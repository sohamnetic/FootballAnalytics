"""
Coarse team assignment from jersey colour.

Assigns each person stable_id to team_a, team_b, referee, or unknown.
This is NOT exact player identification. Sports ball rows are ignored.
"""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from config.config import (
    TEAM_AMBIGUOUS_RATIO,
    TEAM_ASSIGN_MIN_CONFIDENCE,
    TEAM_DET_MIN_CONFIDENCE,
    TEAM_MAX_SAMPLES_PER_ID,
    TEAM_MIN_SAMPLES,
    TEAM_OUTPUT,
    TEAM_REFEREE_MIN_CENTROID_DIST,
    TEAM_SAMPLE_STRIDE,
)

from scripts.vision.jersey_color import JerseyColorExtractor

PERSON_CLASS = "person"
TEAM_A = "team_a"
TEAM_B = "team_b"
REFEREE = "referee"
UNKNOWN = "unknown"


def _color_feature(bgr):
    """
    Cluster feature from BGR via HSV.

    Hue is encoded as (cos, sin) weighted by saturation so wraparound
    is handled and grey/dark kits sit near the origin. Lab can replace
    this later without changing assignment I/O.
    """
    h, s, v = JerseyColorExtractor.bgr_to_hsv(bgr)
    angle = (h / 180.0) * 2.0 * math.pi
    sat = s / 255.0
    val = v / 255.0
    return np.array(
        [math.cos(angle) * sat, math.sin(angle) * sat, val],
        dtype=np.float32,
    )


def _bgr_to_hex(bgr):
    b, g, r = [int(x) for x in bgr]
    return f"#{r:02x}{g:02x}{b:02x}"


def _format_bgr(bgr):
    return f"{int(bgr[0])},{int(bgr[1])},{int(bgr[2])}"


def collect_jersey_samples(
    csv_path,
    video_path,
    stride=TEAM_SAMPLE_STRIDE,
    min_confidence=TEAM_DET_MIN_CONFIDENCE,
    max_per_id=TEAM_MAX_SAMPLES_PER_ID,
):
    df = pd.read_csv(csv_path)
    people = df[df["class"] == PERSON_CLASS].copy()
    people = people[people["confidence"] >= min_confidence]
    people = people.dropna(subset=["stable_id"])
    people["stable_id"] = people["stable_id"].astype(int)

    all_stable_ids = sorted(people["stable_id"].unique().tolist())

    min_frame = int(people["frame"].min())
    by_frame = defaultdict(list)
    for _, row in people.iterrows():
        frame = int(row["frame"])
        if (frame - min_frame) % stride != 0:
            continue
        by_frame[frame].append(row)

    extractor = JerseyColorExtractor()
    samples = defaultdict(list)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    frames = sorted(by_frame.keys())
    if not frames:
        cap.release()
        return samples

    start_frame = frames[0]
    end_frame = frames[-1]
    wanted = set(frames)
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(start_frame - 1, 0))
    current = start_frame
    while current <= end_frame:
        ret, image = cap.read()
        if not ret:
            break
        if current in wanted:
            for row in by_frame[current]:
                sid = int(row["stable_id"])
                if len(samples[sid]) >= max_per_id:
                    continue
                bbox = (
                    int(row["x1"]),
                    int(row["y1"]),
                    int(row["x2"]),
                    int(row["y2"]),
                )
                color = extractor.extract_color(image, bbox)
                if color is None:
                    continue
                samples[sid].append(color)
        current += 1

    cap.release()
    for sid in all_stable_ids:
        samples.setdefault(sid, [])
    return samples


def _robust_representative(colors):
    """Median BGR after dropping hue outliers when possible."""
    if not colors:
        return None, 0.0

    arr = np.array(colors, dtype=np.float32)
    if len(colors) < 3:
        med = np.median(arr, axis=0)
        return tuple(int(x) for x in med), 0.4

    hues = np.array(
        [JerseyColorExtractor.bgr_to_hsv(c)[0] for c in colors],
        dtype=np.float32,
    )
    median_h = np.median(hues)
    circ = np.minimum(np.abs(hues - median_h), 180 - np.abs(hues - median_h))
    mad = np.median(circ) + 1e-6
    keep = circ <= max(25.0, 3.0 * mad)
    if keep.sum() < 3:
        keep = np.ones(len(colors), dtype=bool)
    filtered = arr[keep]
    med = np.median(filtered, axis=0)
    consistency = 1.0 - min(1.0, float(np.mean(circ[keep])) / 90.0)
    return tuple(int(x) for x in med), max(0.0, consistency)


def _kmeans_two(features):
    data = np.float32(features)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 40, 0.5)
    _, labels, centers = cv2.kmeans(
        data,
        2,
        None,
        criteria,
        5,
        cv2.KMEANS_PP_CENTERS,
    )
    return labels.flatten(), centers


def _is_yellow_kit(bgr):
    h, s, v = JerseyColorExtractor.bgr_to_hsv(bgr)
    return 18 <= h <= 40 and s >= 80 and v >= 80


def assign_teams(samples, min_samples=TEAM_MIN_SAMPLES):
    all_ids = sorted(samples.keys())
    reps = {}
    consistencies = {}
    for sid in all_ids:
        rep, consistency = _robust_representative(samples[sid])
        reps[sid] = rep
        consistencies[sid] = consistency

    clusterable = [
        sid for sid in all_ids
        if reps[sid] is not None and len(samples[sid]) >= min_samples
    ]

    assignments = {}
    if len(clusterable) < 4:
        for sid in all_ids:
            assignments[sid] = {
                "team_id": UNKNOWN,
                "confidence": 0.2,
                "reason": "insufficient clusterable identities",
            }
        return assignments, reps, None, None

    features = np.stack([_color_feature(reps[sid]) for sid in clusterable])
    labels, centers = _kmeans_two(features)

    # Label clusters by mean hue so team_a / team_b are stable-ish across runs.
    cluster_hues = []
    for k in (0, 1):
        members = [clusterable[i] for i, lab in enumerate(labels) if lab == k]
        hues = [JerseyColorExtractor.bgr_to_hsv(reps[sid])[0] for sid in members]
        cluster_hues.append(float(np.mean(hues)) if hues else 0.0)
    if cluster_hues[0] <= cluster_hues[1]:
        cluster_to_team = {0: TEAM_A, 1: TEAM_B}
    else:
        cluster_to_team = {0: TEAM_B, 1: TEAM_A}

    team_centers = {
        cluster_to_team[0]: centers[0],
        cluster_to_team[1]: centers[1],
    }

    for i, sid in enumerate(clusterable):
        feat = features[i]
        d_a = float(np.linalg.norm(feat - team_centers[TEAM_A]))
        d_b = float(np.linalg.norm(feat - team_centers[TEAM_B]))
        nearest = TEAM_A if d_a <= d_b else TEAM_B
        other = TEAM_B if nearest == TEAM_A else TEAM_A
        d_near = min(d_a, d_b)
        d_far = max(d_a, d_b)
        ratio = d_near / max(d_far, 1e-6)
        sample_n = len(samples[sid])
        sample_score = min(1.0, sample_n / 20.0)
        consistency = consistencies[sid]
        conf = round(0.45 * (1.0 - ratio) + 0.35 * consistency + 0.20 * sample_score, 3)

        if _is_yellow_kit(reps[sid]) and d_near >= TEAM_REFEREE_MIN_CENTROID_DIST:
            assignments[sid] = {
                "team_id": REFEREE,
                "confidence": min(0.9, max(conf, 0.55)),
                "reason": "distinct kit (yellow-like, far from team centres)",
            }
            continue

        if d_near >= TEAM_REFEREE_MIN_CENTROID_DIST and ratio > TEAM_AMBIGUOUS_RATIO:
            assignments[sid] = {
                "team_id": REFEREE if _is_yellow_kit(reps[sid]) else UNKNOWN,
                "confidence": round(conf * 0.6, 3),
                "reason": "far from both team colour centres",
            }
            continue

        if ratio > TEAM_AMBIGUOUS_RATIO or conf < TEAM_ASSIGN_MIN_CONFIDENCE:
            assignments[sid] = {
                "team_id": UNKNOWN,
                "confidence": conf,
                "reason": "ambiguous / similar distance to both teams",
            }
            continue

        assignments[sid] = {
            "team_id": nearest,
            "confidence": conf,
            "reason": "consistent jersey colour",
        }

    for sid in all_ids:
        if sid in assignments:
            continue
        n = len(samples[sid])
        if n == 0 or reps[sid] is None:
            assignments[sid] = {
                "team_id": UNKNOWN,
                "confidence": 0.1,
                "reason": "no usable jersey samples",
            }
        else:
            assignments[sid] = {
                "team_id": UNKNOWN,
                "confidence": round(0.15 + 0.02 * n, 3),
                "reason": "insufficient samples",
            }

    return assignments, reps, team_centers, clusterable


def write_player_teams_csv(assignments, samples, reps, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "stable_id",
        "team_id",
        "sample_count",
        "representative_color",
        "confidence",
        "reason",
    ]
    rows = []
    for sid in sorted(assignments):
        rep = reps.get(sid)
        color = _format_bgr(rep) if rep is not None else ""
        rows.append({
            "stable_id": sid,
            "team_id": assignments[sid]["team_id"],
            "sample_count": len(samples.get(sid, [])),
            "representative_color": color,
            "confidence": assignments[sid]["confidence"],
            "reason": assignments[sid]["reason"],
        })
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return output_path, rows


def write_team_swatches(rows, reps, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cell_w, cell_h = 220, 36
    height = max(cell_h * (len(rows) + 1), cell_h)
    image = np.full((height, cell_w + 420, 3), 30, dtype=np.uint8)
    team_bgr = {
        TEAM_A: (40, 40, 200),
        TEAM_B: (200, 80, 40),
        REFEREE: (0, 220, 220),
        UNKNOWN: (90, 90, 90),
    }
    y = 4
    for row in rows:
        sid = row["stable_id"]
        team = row["team_id"]
        rep = reps.get(sid)
        color = tuple(int(x) for x in rep) if rep is not None else (40, 40, 40)
        cv2.rectangle(image, (4, y), (70, y + cell_h - 6), color, -1)
        cv2.rectangle(image, (80, y), (140, y + cell_h - 6), team_bgr.get(team, (90, 90, 90)), -1)
        text = f"id {sid}  {team}  n={row['sample_count']}  c={row['confidence']}"
        cv2.putText(
            image, text, (150, y + 22),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (240, 240, 240), 1, cv2.LINE_AA,
        )
        y += cell_h
    cv2.imwrite(str(output_path), image)
    return output_path


def write_team_overlay_video(csv_path, video_path, assignments, output_path, max_frames=None):
    """Draw person boxes coloured by assigned team. No YOLO."""
    df = pd.read_csv(csv_path)
    people = df[df["class"] == PERSON_CLASS].copy()
    people = people.dropna(subset=["stable_id"])
    people["stable_id"] = people["stable_id"].astype(int)

    by_frame = defaultdict(list)
    for _, row in people.iterrows():
        by_frame[int(row["frame"])].append(row)

    frames = sorted(by_frame.keys())
    if not frames:
        return None

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    colors = {
        TEAM_A: (40, 40, 220),
        TEAM_B: (220, 90, 40),
        REFEREE: (0, 220, 220),
        UNKNOWN: (160, 160, 160),
    }

    min_frame, max_frame = frames[0], frames[-1]
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(min_frame - 1, 0))
    written = 0
    frame_index = min_frame
    while frame_index <= max_frame:
        ret, image = cap.read()
        if not ret:
            break
        for row in by_frame.get(frame_index, []):
            sid = int(row["stable_id"])
            team = assignments.get(sid, {}).get("team_id", UNKNOWN)
            color = colors.get(team, colors[UNKNOWN])
            x1, y1, x2, y2 = map(int, (row["x1"], row["y1"], row["x2"], row["y2"]))
            cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                image, f"{sid} {team}", (x1, max(16, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA,
            )
        writer.write(image)
        written += 1
        frame_index += 1
        if max_frames is not None and written >= max_frames:
            break

    cap.release()
    writer.release()
    return output_path


def summarize_assignments(rows, reps):
    counts = {TEAM_A: 0, TEAM_B: 0, REFEREE: 0, UNKNOWN: 0}
    team_colors = {TEAM_A: [], TEAM_B: []}
    ambiguous = 0
    for row in rows:
        team = row["team_id"]
        counts[team] = counts.get(team, 0) + 1
        if team in (UNKNOWN,) or "ambiguous" in row["reason"] or "insufficient" in row["reason"]:
            ambiguous += 1
        sid = row["stable_id"]
        if team in team_colors and reps.get(sid) is not None:
            team_colors[team].append(reps[sid])

    def mean_color(colors):
        if not colors:
            return None
        arr = np.mean(np.array(colors, dtype=np.float32), axis=0)
        bgr = tuple(int(x) for x in arr)
        return f"{_format_bgr(bgr)} ({_bgr_to_hex(bgr)})"

    return {
        "total": len(rows),
        "team_a": counts[TEAM_A],
        "team_b": counts[TEAM_B],
        "referee": counts[REFEREE],
        "unknown": counts[UNKNOWN],
        "ambiguous": ambiguous,
        "team_a_color": mean_color(team_colors[TEAM_A]),
        "team_b_color": mean_color(team_colors[TEAM_B]),
    }


def run_team_assignment(
    csv_path,
    video_path,
    output_csv=None,
    write_overlay=True,
    overlay_max_frames=None,
):
    TEAM_OUTPUT.mkdir(parents=True, exist_ok=True)
    csv_path = Path(csv_path)
    output_csv = Path(output_csv) if output_csv else TEAM_OUTPUT / "player_teams.csv"

    print("Collecting jersey samples (person rows only)...")
    samples = collect_jersey_samples(csv_path, video_path)
    assignments, reps, _centers, _clusterable = assign_teams(samples)
    csv_out, rows = write_player_teams_csv(assignments, samples, reps, output_csv)
    canonical = TEAM_OUTPUT / "player_teams.csv"
    if Path(csv_out).resolve() != canonical.resolve():
        write_player_teams_csv(assignments, samples, reps, canonical)
    swatch_path = write_team_swatches(rows, reps, TEAM_OUTPUT / "team_swatches.png")

    overlay_path = None
    if write_overlay:
        overlay_path = write_team_overlay_video(
            csv_path,
            video_path,
            assignments,
            TEAM_OUTPUT / "team_validation.mp4",
            max_frames=overlay_max_frames,
        )

    summary = summarize_assignments(rows, reps)
    print("Team assignment:")
    print(f"  total stable IDs : {summary['total']}")
    print(f"  team_a           : {summary['team_a']}  colour {summary['team_a_color']}")
    print(f"  team_b           : {summary['team_b']}  colour {summary['team_b_color']}")
    print(f"  referee          : {summary['referee']}")
    print(f"  unknown          : {summary['unknown']}")
    print(f"  ambiguous/weak   : {summary['ambiguous']}")
    print(f"  CSV              : {csv_out}")
    print(f"  swatches         : {swatch_path}")
    if overlay_path:
        print(f"  overlay video    : {overlay_path}")

    return {
        "csv": csv_out,
        "rows": rows,
        "assignments": assignments,
        "summary": summary,
        "swatches": swatch_path,
        "overlay": overlay_path,
    }
