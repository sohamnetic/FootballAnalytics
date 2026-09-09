"""
Ball time series and nearest-player possession (Phase 1).

Person and sports ball use separate IdentityManagers, so this module
always filters by class before using stable_id.

Ball position is bbox centre (x1+x2)/2, (y1+y2)/2 — not CSV center_x/y.
Player position remains CSV center_x/y (feet / bbox bottom-centre).
"""

from __future__ import annotations

import csv
import math
from pathlib import Path

import cv2
import pandas as pd

from config.config import (
    EVENTS_OUTPUT,
    MAX_BALL_INTERPOLATION_GAP,
    MAX_POSSESSION_DISTANCE_PX,
    POSSESSION_CONFIRM_FRAMES,
)

FRAME_STATE_CSV = EVENTS_OUTPUT / "frame_state.csv"
POSSESSION_VIDEO = EVENTS_OUTPUT / "possession_validation.mp4"

PERSON_CLASS = "person"
BALL_CLASS = "sports ball"


def _as_int_id(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        number = float(value)
        if math.isnan(number):
            return None
        return int(number)
    except (TypeError, ValueError):
        text = str(value).strip()
        return text if text else None


def _format_optional(value, digits=None):
    if value is None:
        return ""
    if digits is not None:
        return f"{float(value):.{digits}f}"
    return str(value)


class PossessionEngine:
    def __init__(
        self,
        csv_path,
        fps,
        max_interpolation_gap=MAX_BALL_INTERPOLATION_GAP,
        max_possession_distance_px=MAX_POSSESSION_DISTANCE_PX,
        confirm_frames=POSSESSION_CONFIRM_FRAMES,
    ):
        self.csv_path = Path(csv_path)
        self.fps = float(fps)
        self.max_interpolation_gap = int(max_interpolation_gap)
        self.max_possession_distance_px = float(max_possession_distance_px)
        self.confirm_frames = int(confirm_frames)
        self.df = pd.read_csv(self.csv_path)

    def _dedupe_frame(self, group):
        if "confidence" in group.columns:
            group = group.sort_values("confidence", ascending=False)
        return group.drop_duplicates(subset=["stable_id"], keep="first")

    def _players_by_frame(self):
        people = self.df[self.df["class"] == PERSON_CLASS].copy()
        by_frame = {}
        if people.empty:
            return by_frame
        for frame, group in people.groupby("frame"):
            group = self._dedupe_frame(group)
            players = []
            for _, row in group.iterrows():
                sid = _as_int_id(row.get("stable_id"))
                if sid is None:
                    continue
                players.append({
                    "stable_id": sid,
                    "x": float(row["center_x"]),
                    "y": float(row["center_y"]),
                    "x1": int(row["x1"]),
                    "y1": int(row["y1"]),
                    "x2": int(row["x2"]),
                    "y2": int(row["y2"]),
                    "confidence": float(row["confidence"]),
                })
            by_frame[int(frame)] = players
        return by_frame

    def _detected_balls(self):
        balls = self.df[self.df["class"] == BALL_CLASS].copy()
        detected = {}
        if balls.empty:
            return detected
        for frame, group in balls.groupby("frame"):
            row = group.sort_values("confidence", ascending=False).iloc[0]
            detected[int(frame)] = {
                "x": (float(row["x1"]) + float(row["x2"])) / 2.0,
                "y": (float(row["y1"]) + float(row["y2"])) / 2.0,
                "confidence": float(row["confidence"]),
            }
        return detected

    def _ball_series(self, min_frame, max_frame, detected):
        series = {frame: None for frame in range(min_frame, max_frame + 1)}
        for frame, ball in detected.items():
            series[frame] = {
                "x": ball["x"],
                "y": ball["y"],
                "confidence": ball["confidence"],
                "source": "detected",
            }

        frames = sorted(detected.keys())
        for i in range(len(frames) - 1):
            start, end = frames[i], frames[i + 1]
            gap = end - start - 1
            if gap <= 0 or gap > self.max_interpolation_gap:
                continue
            x0, y0, c0 = detected[start]["x"], detected[start]["y"], detected[start]["confidence"]
            x1, y1, c1 = detected[end]["x"], detected[end]["y"], detected[end]["confidence"]
            for step in range(1, gap + 1):
                t = step / (gap + 1)
                series[start + step] = {
                    "x": x0 + t * (x1 - x0),
                    "y": y0 + t * (y1 - y0),
                    "confidence": c0 + t * (c1 - c0),
                    "source": "interpolated",
                }
        return series

    def _nearest_player(self, ball, players):
        if ball is None or not players:
            return None, None
        best_id = None
        best_dist = None
        for player in players:
            dist = math.dist((ball["x"], ball["y"]), (player["x"], player["y"]))
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_id = player["stable_id"]
        return best_id, best_dist

    def build_frame_states(self):
        if self.df.empty:
            return []

        min_frame = int(self.df["frame"].min())
        max_frame = int(self.df["frame"].max())
        players_by_frame = self._players_by_frame()
        detected = self._detected_balls()
        ball_series = self._ball_series(min_frame, max_frame, detected)

        confirmed = None
        pending_id = None
        pending_count = 0
        rows = []

        for frame in range(min_frame, max_frame + 1):
            ball = ball_series[frame]
            players = players_by_frame.get(frame, [])

            if ball is None:
                nearest_id, nearest_dist = None, None
                pending_id = None
                pending_count = 0
                possession_state = "unknown"
                possessor = None
            else:
                nearest_id, nearest_dist = self._nearest_player(ball, players)
                in_range = (
                    nearest_id is not None
                    and nearest_dist is not None
                    and nearest_dist <= self.max_possession_distance_px
                )

                if not in_range:
                    target = None
                else:
                    target = nearest_id

                if target == pending_id:
                    pending_count += 1
                else:
                    pending_id = target
                    pending_count = 1

                if pending_id is not None and pending_count >= self.confirm_frames:
                    confirmed = pending_id
                    possession_state = "confirmed"
                    possessor = confirmed
                elif pending_id is None and pending_count >= self.confirm_frames:
                    confirmed = None
                    possession_state = "loose"
                    possessor = None
                elif pending_id is None:
                    possession_state = "loose"
                    possessor = confirmed
                else:
                    possession_state = "candidate"
                    possessor = confirmed

            time_s = (frame - 1) / self.fps
            rows.append({
                "frame": frame,
                "time_s": round(time_s, 4),
                "ball_x": None if ball is None else round(ball["x"], 2),
                "ball_y": None if ball is None else round(ball["y"], 2),
                "ball_source": "missing" if ball is None else ball["source"],
                "ball_confidence": (
                    None if ball is None else round(ball["confidence"], 4)
                ),
                "nearest_player_stable_id": nearest_id,
                "nearest_player_distance_px": (
                    None if nearest_dist is None else round(nearest_dist, 2)
                ),
                "possessor_stable_id": possessor,
                "possession_state": possession_state,
            })

        return rows

    def write_frame_state_csv(self, rows, output_path=FRAME_STATE_CSV):
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "frame",
            "time_s",
            "ball_x",
            "ball_y",
            "ball_source",
            "ball_confidence",
            "nearest_player_stable_id",
            "nearest_player_distance_px",
            "possessor_stable_id",
            "possession_state",
        ]
        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    key: _format_optional(row[key]) for key in fieldnames
                })
        return output_path


def summarize_frame_states(rows):
    total = len(rows)
    detected = sum(1 for r in rows if r["ball_source"] == "detected")
    interpolated = sum(1 for r in rows if r["ball_source"] == "interpolated")
    missing = sum(1 for r in rows if r["ball_source"] == "missing")
    confirmed = sum(1 for r in rows if r["possession_state"] == "confirmed")
    candidate = sum(1 for r in rows if r["possession_state"] == "candidate")
    loose = sum(1 for r in rows if r["possession_state"] == "loose")
    unknown = sum(1 for r in rows if r["possession_state"] == "unknown")
    possessors = sorted({
        r["possessor_stable_id"]
        for r in rows
        if r["possessor_stable_id"] is not None
    })
    return {
        "total_frames": total,
        "ball_detected_frames": detected,
        "interpolated_frames": interpolated,
        "missing_ball_frames": missing,
        "confirmed_possession_frames": confirmed,
        "candidate_frames": candidate,
        "loose_ball_frames": loose,
        "unknown_frames": unknown,
        "unique_possessors": possessors,
    }


def write_possession_video(
    video_path,
    csv_path,
    rows,
    output_path=POSSESSION_VIDEO,
):
    video_path = Path(video_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(csv_path)
    people = df[df["class"] == PERSON_CLASS]
    boxes_by_frame = {}
    for frame, group in people.groupby("frame"):
        boxes = {}
        group = group.sort_values("confidence", ascending=False)
        for _, row in group.iterrows():
            sid = _as_int_id(row.get("stable_id"))
            if sid is None or sid in boxes:
                continue
            boxes[sid] = (
                int(row["x1"]), int(row["y1"]),
                int(row["x2"]), int(row["y2"]),
            )
        boxes_by_frame[int(frame)] = boxes

    state_by_frame = {row["frame"]: row for row in rows}

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if not state_by_frame:
        cap.release()
        raise RuntimeError("No possession rows to visualise")

    min_frame = min(state_by_frame.keys())
    max_frame = max(state_by_frame.keys())
    first_state = state_by_frame[min_frame]
    last_state = state_by_frame[max_frame]
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(min_frame - 1, 0))

    writer = cv2.VideoWriter(
        str(output_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        cap.release()
        raise RuntimeError(f"Cannot write video: {output_path}")

    frame_index = min_frame
    while frame_index <= max_frame:
        ret, image = cap.read()
        if not ret:
            break

        state = state_by_frame.get(frame_index)
        if state is None:
            writer.write(image)
            frame_index += 1
            continue

        boxes = boxes_by_frame.get(frame_index, {})
        nearest = state["nearest_player_stable_id"]
        possessor = state["possessor_stable_id"]

        if nearest in boxes:
            x1, y1, x2, y2 = boxes[nearest]
            cv2.rectangle(image, (x1, y1), (x2, y2), (255, 180, 0), 2)
            cv2.putText(
                image, f"near {nearest}", (x1, max(20, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 180, 0), 2, cv2.LINE_AA,
            )

        if possessor in boxes and possessor != nearest:
            x1, y1, x2, y2 = boxes[possessor]
            cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)

        if possessor in boxes:
            x1, y1, x2, y2 = boxes[possessor]
            cv2.putText(
                image, f"poss {possessor}", (x1, y2 + 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA,
            )

        if state["ball_x"] is not None and state["ball_y"] is not None:
            bx, by = int(state["ball_x"]), int(state["ball_y"])
            color = (0, 255, 255) if state["ball_source"] == "detected" else (255, 255, 0)
            cv2.circle(image, (bx, by), 8, color, -1)
            cv2.circle(image, (bx, by), 12, (0, 0, 0), 2)
            if state["ball_source"] == "interpolated":
                cv2.putText(
                    image, "INTERP", (bx + 14, by - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2, cv2.LINE_AA,
                )

        lines = [
            f"src {first_state['time_s']:.1f}s-{last_state['time_s']:.1f}s",
            f"frame {frame_index}  t={state['time_s']:.3f}s",
            f"ball {state['ball_source']}",
            f"nearest {state['nearest_player_stable_id']}  d={state['nearest_player_distance_px']}",
            f"possessor {state['possessor_stable_id']}",
            f"state {state['possession_state']}",
        ]
        y = 28
        for line in lines:
            cv2.putText(
                image, line, (16, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4, cv2.LINE_AA,
            )
            cv2.putText(
                image, line, (16, y),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA,
            )
            y += 28

        writer.write(image)
        frame_index += 1

    cap.release()
    writer.release()
    return output_path


def run_possession(
    csv_path,
    video_path,
    fps=None,
    write_video=True,
    frame_state_csv=None,
    validation_video=None,
):
    csv_path = Path(csv_path)
    video_path = Path(video_path)
    EVENTS_OUTPUT.mkdir(parents=True, exist_ok=True)
    frame_state_csv = Path(frame_state_csv) if frame_state_csv else FRAME_STATE_CSV
    validation_video = Path(validation_video) if validation_video else POSSESSION_VIDEO

    if fps is None:
        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        if fps is None or fps <= 0:
            raise RuntimeError(f"Cannot read FPS from {video_path}")

    engine = PossessionEngine(csv_path, fps)
    rows = engine.build_frame_states()
    csv_out = engine.write_frame_state_csv(rows, frame_state_csv)
    stats = summarize_frame_states(rows)

    video_out = None
    if write_video:
        if not rows:
            print("Skipping possession video: no frame_state rows")
        else:
            video_out = write_possession_video(
                video_path, csv_path, rows, validation_video,
            )

    print("Possession configuration:")
    print(f"  max interpolation gap     : {engine.max_interpolation_gap} frames")
    print(f"  max possession distance   : {engine.max_possession_distance_px} px")
    print(f"  possession confirm frames : {engine.confirm_frames}")
    print("Possession summary:")
    print(f"  total frames              : {stats['total_frames']}")
    print(f"  ball detected frames      : {stats['ball_detected_frames']}")
    print(f"  interpolated frames       : {stats['interpolated_frames']}")
    print(f"  missing ball frames       : {stats['missing_ball_frames']}")
    print(f"  confirmed possession      : {stats['confirmed_possession_frames']}")
    print(f"  candidate frames          : {stats['candidate_frames']}")
    print(f"  loose-ball frames         : {stats['loose_ball_frames']}")
    print(f"  unknown frames            : {stats['unknown_frames']}")
    print(f"  unique possessors         : {stats['unique_possessors']}")
    print(f"  frame state CSV           : {csv_out}")
    if video_out:
        print(f"  validation video          : {video_out}")

    return {
        "rows": rows,
        "stats": stats,
        "csv": csv_out,
        "video": video_out,
        "engine": engine,
    }
