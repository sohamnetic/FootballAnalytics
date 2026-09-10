"""
Thin MVP pipeline: tracking CSV → MotionEngine analytics → heatmaps.

Default grouping is stable_id when that column exists and has values.
MotionEngine still defaults to track_id for older tests/scripts.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import cv2
import pandas as pd

from config.config import (
    COORDINATE_OUTPUT,
    EVENTS_OUTPUT,
    HEATMAP_OUTPUT,
    IDENTITY_OUTPUT,
    OUTPUT_DIR,
    TEAM_OUTPUT,
    TEST_VIDEO,
)

from scripts.analytics.events.passes import run_pass_detection
from scripts.analytics.events.possession import run_possession
from scripts.analytics.events.shots import run_shot_detection
from scripts.analytics.events.turnovers import run_turnover_detection
from scripts.analytics.match_stats import run_match_stats
from scripts.analytics.heatmap import HeatmapEngine
from scripts.analytics.motion_engine import MotionEngine
from scripts.track import run_tracking
from scripts.vision.team_assigner import run_team_assignment

ANALYTICS_DIR = OUTPUT_DIR / "analytics"
ANALYTICS_CSV = ANALYTICS_DIR / "player_analytics.csv"


def _format_tag_number(value):
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return str(value).replace(".", "p")


def segment_suffix(start_time, duration):
    """Empty for a full-video run (start 0, no duration)."""
    start_time = float(start_time or 0)
    if start_time == 0 and duration is None:
        return ""
    tag = f"t{_format_tag_number(start_time)}"
    if duration is not None:
        tag += f"_d{_format_tag_number(duration)}"
    return tag


def default_coordinate_csv(video_path: Path, start_time=0, duration=None) -> Path:
    suffix = segment_suffix(start_time, duration)
    stem = video_path.stem
    name = f"{stem}_{suffix}.csv" if suffix else f"{stem}.csv"
    return COORDINATE_OUTPUT / name


def segment_output_paths(start_time=0, duration=None):
    suffix = segment_suffix(start_time, duration)
    if not suffix:
        return {
            "analytics_csv": ANALYTICS_CSV,
            "heatmap_dir": HEATMAP_OUTPUT,
            "frame_state_csv": EVENTS_OUTPUT / "frame_state.csv",
            "possession_video": EVENTS_OUTPUT / "possession_validation.mp4",
            "tracking_name": "match_tracking",
            "teams_csv": TEAM_OUTPUT / "player_teams.csv",
            "teams_overlay": TEAM_OUTPUT / "team_validation.mp4",
            "passes_suffix": "",
        }
    return {
        "analytics_csv": ANALYTICS_DIR / f"player_analytics_{suffix}.csv",
        "heatmap_dir": HEATMAP_OUTPUT / suffix,
        "frame_state_csv": EVENTS_OUTPUT / f"frame_state_{suffix}.csv",
        "possession_video": EVENTS_OUTPUT / f"possession_validation_{suffix}.mp4",
        "tracking_name": f"match_tracking_{suffix}",
        "teams_csv": TEAM_OUTPUT / f"player_teams_{suffix}.csv",
        "teams_overlay": TEAM_OUTPUT / f"team_validation_{suffix}.mp4",
        "passes_suffix": suffix,
    }


def _video_fps_and_shape(video_path: Path):
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    ret, frame = cap.read()
    cap.release()

    if not ret or fps is None or fps <= 0:
        raise RuntimeError(f"Cannot read video or FPS: {video_path}")

    return float(fps), frame.shape


def choose_identity_column(csv_path: Path):
    """
    Use stable_id when the coordinate CSV has non-empty values.
    Fall back to track_id for older CSVs without identity.
    """
    df = pd.read_csv(csv_path)
    if "stable_id" in df.columns:
        values = df["stable_id"].dropna()
        values = values[values.astype(str).str.strip() != ""]
        if len(values) > 0:
            return "stable_id"
    return "track_id"


def _format_id(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    try:
        number = float(value)
        if number.is_integer():
            return str(int(number))
    except (TypeError, ValueError):
        pass
    return str(value)


def _track_ids_seen(motion: MotionEngine, player_id) -> str:
    if "track_id" not in motion.df.columns:
        return ""
    subset = motion.df[motion.df[motion.identity_column] == player_id]
    ids = []
    for track_id in subset["track_id"].dropna().unique().tolist():
        formatted = _format_id(track_id)
        if formatted:
            ids.append(formatted)
    return ";".join(ids)


def _frames_detected(motion: MotionEngine, player_id) -> int:
    return len(motion._player_rows(player_id))


def _finite_points(points):
    """Drop NaN coordinates from short tracks (rolling smooth + fill)."""
    cleaned = []
    for x, y in points:
        if x is None or y is None:
            continue
        fx, fy = float(x), float(y)
        if math.isnan(fx) or math.isnan(fy):
            continue
        cleaned.append((fx, fy))
    return cleaned


def _finite_values(values):
    return [float(v) for v in values if v is not None and not math.isnan(float(v))]


def _clear_player_heatmaps(heatmap_dir: Path):
    for path in heatmap_dir.glob("player_*.png"):
        path.unlink()


def run_analytics(csv_path: Path, video_path: Path, analytics_csv=None, heatmap_dir=None):
    analytics_csv = Path(analytics_csv) if analytics_csv else ANALYTICS_CSV
    heatmap_dir = Path(heatmap_dir) if heatmap_dir else HEATMAP_OUTPUT

    ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)
    heatmap_dir.mkdir(parents=True, exist_ok=True)

    identity_column = choose_identity_column(csv_path)
    if identity_column == "stable_id":
        print("Analytics identity: stable_id")
    else:
        print("Analytics identity: track_id (fallback: stable_id not available)")

    fps, frame_shape = _video_fps_and_shape(video_path)
    motion = MotionEngine(csv_path, fps, identity_column=identity_column)
    heatmap_engine = HeatmapEngine(frame_shape)

    _clear_player_heatmaps(heatmap_dir)

    player_ids = motion.get_all_players()
    rows = []
    heatmap_paths = []

    for player_id in player_ids:
        distance = motion.get_distance(player_id)
        if distance is None or math.isnan(float(distance)):
            distance = 0.0

        speeds = _finite_values(motion.get_speed(player_id))
        frames = _frames_detected(motion, player_id)
        track_ids_seen = _track_ids_seen(motion, player_id)

        if identity_column == "stable_id":
            stable_id = _format_id(player_id)
        else:
            stable_id = ""

        if speeds:
            avg_speed = sum(speeds) / len(speeds)
            max_speed = max(speeds)
        else:
            avg_speed = 0.0
            max_speed = 0.0

        rows.append({
            "stable_id": stable_id,
            "track_ids_seen": track_ids_seen,
            "frames_detected": frames,
            "distance_pixels": round(distance, 4),
            "average_speed_px_per_sec": round(avg_speed, 4),
            "maximum_speed_px_per_sec": round(max_speed, 4),
        })

        trajectory = _finite_points(motion.get_smoothed_trajectory(player_id))
        heat = heatmap_engine.generate(trajectory)
        if identity_column == "stable_id":
            heat_path = heatmap_dir / f"player_stable_{stable_id}.png"
        else:
            heat_path = heatmap_dir / f"player_{_format_id(player_id)}.png"
        cv2.imwrite(str(heat_path), heat)
        heatmap_paths.append(heat_path)

    analytics_csv.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "stable_id",
        "track_ids_seen",
        "frames_detected",
        "distance_pixels",
        "average_speed_px_per_sec",
        "maximum_speed_px_per_sec",
    ]

    with open(analytics_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return rows, heatmap_paths, identity_column, analytics_csv, heatmap_dir


def run_mvp(
    video_path: Path,
    csv_path: Path,
    force_track: bool,
    max_frames=None,
    skip_events: bool = False,
    skip_teams: bool = False,
    skip_passes: bool = False,
    skip_turnovers: bool = False,
    skip_shots: bool = False,
    skip_match_stats: bool = False,
    start_time=0,
    duration=None,
):
    csv_path = Path(csv_path)
    video_path = Path(video_path)
    paths = segment_output_paths(start_time, duration)

    if force_track or not csv_path.exists():
        print(f"Running tracking → {csv_path}")
        csv_path = Path(
            run_tracking(
                video_path=video_path,
                coordinate_output=csv_path,
                max_frames=max_frames,
                start_time=start_time,
                duration=duration,
                tracking_name=paths["tracking_name"],
            )
        )
    else:
        print(f"Reusing existing coordinate CSV: {csv_path}")

    if not csv_path.exists():
        raise FileNotFoundError(f"Coordinate CSV was not created: {csv_path}")

    print("Running analytics (MotionEngine)...")
    rows, heatmap_paths, identity_column, analytics_csv, heatmap_dir = run_analytics(
        csv_path,
        video_path,
        analytics_csv=paths["analytics_csv"],
        heatmap_dir=paths["heatmap_dir"],
    )

    possession_result = None
    if not skip_events:
        print("Running possession (Phase 1, no YOLO)...")
        possession_result = run_possession(
            csv_path,
            video_path,
            frame_state_csv=paths["frame_state_csv"],
            validation_video=paths["possession_video"],
        )

    team_result = None
    if not skip_teams:
        print("Running team assignment (jersey colour, no YOLO)...")
        team_result = run_team_assignment(
            csv_path,
            video_path,
            output_csv=paths["teams_csv"],
            write_overlay=True,
        )

    pass_result = None
    frame_state_csv = paths["frame_state_csv"]
    teams_csv = paths["teams_csv"]
    if Path(teams_csv).exists() is False and (TEAM_OUTPUT / "player_teams.csv").exists():
        teams_csv = TEAM_OUTPUT / "player_teams.csv"
    if not skip_passes and Path(frame_state_csv).exists() and Path(teams_csv).exists():
        print("Running pass detection (post-process, no YOLO)...")
        pass_result = run_pass_detection(
            frame_state_csv,
            teams_csv,
            video_path,
            suffix=paths.get("passes_suffix", ""),
        )

    turnover_result = None
    if not skip_turnovers and Path(frame_state_csv).exists() and Path(teams_csv).exists():
        print("Running interceptions/recoveries (post-process, no YOLO)...")
        turnover_result = run_turnover_detection(
            frame_state_csv,
            teams_csv,
            video_path,
            suffix=paths.get("passes_suffix", ""),
        )

    shot_result = None
    if not skip_shots and Path(frame_state_csv).exists() and Path(teams_csv).exists():
        print("Running shot/on-target/goal detection (post-process, no YOLO)...")
        shot_result = run_shot_detection(
            frame_state_csv,
            teams_csv,
            video_path,
            suffix=paths.get("passes_suffix", ""),
        )

    match_stats_result = None
    suffix = paths.get("passes_suffix", "")
    tag = f"_{suffix}" if suffix else ""
    if not skip_match_stats and Path(frame_state_csv).exists() and Path(teams_csv).exists():
        print("Building match stats (product data layer, no YOLO)...")
        match_stats_result = run_match_stats(
            frame_state_csv=frame_state_csv,
            teams_csv=teams_csv,
            passes_csv=EVENTS_OUTPUT / f"passes{tag}.csv",
            interceptions_csv=EVENTS_OUTPUT / f"interceptions{tag}.csv",
            recoveries_csv=EVENTS_OUTPUT / f"recoveries{tag}.csv",
            shots_csv=EVENTS_OUTPUT / f"shots{tag}.csv",
            video_path=video_path,
            suffix=suffix,
            start_time_s=start_time,
            duration_s=duration,
            identity_audit_csv=IDENTITY_OUTPUT / "identity_audit.csv",
        )

    print("\n" + "=" * 60)
    print("MVP pipeline finished")
    print("=" * 60)
    print(f"Video              : {video_path}")
    print(f"Coordinate CSV     : {csv_path}")
    print(f"Player analytics   : {analytics_csv}")
    print(f"Identity column    : {identity_column}")
    print(f"Players            : {len(rows)}")
    print(f"Heatmaps           : {heatmap_dir}")
    if heatmap_paths:
        print(f"Heatmap files      : {len(heatmap_paths)}")
    if possession_result:
        print(f"Frame state CSV    : {possession_result['csv']}")
        if possession_result.get("video"):
            print(f"Possession video   : {possession_result['video']}")
    if team_result:
        print(f"Player teams CSV   : {team_result['csv']}")
        if team_result.get("overlay"):
            print(f"Team overlay       : {team_result['overlay']}")
    if pass_result:
        print(f"Passes CSV         : {pass_result['passes_csv']}")
        print(f"Pass validation    : {pass_result['validation_csv']}")
    if turnover_result:
        print(f"Interceptions CSV  : {turnover_result['interceptions_csv']}")
        print(f"Recoveries CSV     : {turnover_result['recoveries_csv']}")
    if shot_result:
        print(f"Shots CSV          : {shot_result['shots_csv']}")
        print(f"Shot validation    : {shot_result['validation_csv']}")
    if match_stats_result:
        print(f"Match stats JSON   : {match_stats_result['json']}")
        print(f"Match stats CSV    : {match_stats_result['csv']}")
    print("=" * 60)

    return {
        "csv": csv_path,
        "analytics": analytics_csv,
        "heatmaps": heatmap_paths,
        "heatmap_dir": heatmap_dir,
        "rows": rows,
        "identity_column": identity_column,
        "possession": possession_result,
        "teams": team_result,
        "passes": pass_result,
        "turnovers": turnover_result,
        "shots": shot_result,
        "match_stats": match_stats_result,
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description="Football analytics MVP: track (if needed) then pixel analytics."
    )
    parser.add_argument(
        "--video",
        type=Path,
        default=TEST_VIDEO,
        help="Input video path (default: config TEST_VIDEO)",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Coordinate CSV path. Default: outputs/coordinates/<video_stem>.csv",
    )
    parser.add_argument(
        "--force-track",
        action="store_true",
        help="Run tracking even if the coordinate CSV already exists",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Optional tracking cap (same idea as MAX_FRAMES in track.py)",
    )
    parser.add_argument(
        "--skip-events",
        action="store_true",
        help="Skip Phase 1 possession processing",
    )
    parser.add_argument(
        "--skip-teams",
        action="store_true",
        help="Skip jersey-colour team assignment",
    )
    parser.add_argument(
        "--skip-passes",
        action="store_true",
        help="Skip pass detection post-process",
    )
    parser.add_argument(
        "--skip-turnovers",
        action="store_true",
        help="Skip interception/recovery post-process",
    )
    parser.add_argument(
        "--skip-shots",
        action="store_true",
        help="Skip shot/on-target/goal post-process",
    )
    parser.add_argument(
        "--skip-match-stats",
        action="store_true",
        help="Skip unified match stats aggregation",
    )
    parser.add_argument(
        "--start-time",
        type=float,
        default=0,
        help="Start time in seconds (default: 0). Tracking seeks here.",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Duration in seconds. With --max-frames, stop at the earlier limit.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    video_path = Path(args.video)
    csv_path = args.csv
    if csv_path is None:
        csv_path = default_coordinate_csv(
            video_path,
            start_time=args.start_time,
            duration=args.duration,
        )

    run_mvp(
        video_path=video_path,
        csv_path=csv_path,
        force_track=args.force_track,
        max_frames=args.max_frames,
        skip_events=args.skip_events,
        skip_teams=args.skip_teams,
        skip_passes=args.skip_passes,
        skip_turnovers=args.skip_turnovers,
        skip_shots=args.skip_shots,
        skip_match_stats=args.skip_match_stats,
        start_time=args.start_time,
        duration=args.duration,
    )


if __name__ == "__main__":
    main()
