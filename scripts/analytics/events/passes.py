"""
MVP pass detection from confirmed possession intervals + team assignment.

Does not modify frame_state.csv or possession logic.
stable_id is an MVP identity, not a guaranteed real player.
"""

from __future__ import annotations

import csv
from pathlib import Path

import cv2
import pandas as pd

from config.config import (
    EVENTS_OUTPUT,
    OUTPUT_DIR,
    PASS_MAX_MISSING_BALL_RATIO,
    PASS_MAX_TRANSITION_FRAMES,
    PASS_MIN_POSSESSION_FRAMES,
    TEAM_OUTPUT,
)

VALID_TEAMS = {"team_a", "team_b"}
ANALYTICS_DIR = OUTPUT_DIR / "analytics"


def _int_or_none(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if text == "" or text.lower() == "nan":
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _video_fps(video_path):
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    if fps is None or fps <= 0:
        raise RuntimeError(f"Cannot read FPS from {video_path}")
    return float(fps)


def _load_teams(teams_csv):
    df = pd.read_csv(teams_csv)
    mapping = {}
    for _, row in df.iterrows():
        sid = _int_or_none(row.get("stable_id"))
        if sid is None:
            continue
        team = str(row.get("team_id", "")).strip().lower()
        mapping[sid] = team
    return mapping


def _confirmed_intervals(frame_df):
    """
    Contiguous runs of possession_state == confirmed with the same possessor.
    """
    intervals = []
    current = None

    for _, row in frame_df.sort_values("frame").iterrows():
        state = str(row.get("possession_state", "")).strip().lower()
        possessor = _int_or_none(row.get("possessor_stable_id"))
        frame = int(row["frame"])
        time_s = float(row["time_s"]) if pd.notna(row.get("time_s")) else None

        if state == "confirmed" and possessor is not None:
            if current is None:
                current = {
                    "stable_id": possessor,
                    "start_frame": frame,
                    "end_frame": frame,
                    "start_time_s": time_s,
                    "end_time_s": time_s,
                    "frames": 1,
                }
            elif current["stable_id"] == possessor and frame == current["end_frame"] + 1:
                current["end_frame"] = frame
                current["end_time_s"] = time_s
                current["frames"] += 1
            else:
                intervals.append(current)
                current = {
                    "stable_id": possessor,
                    "start_frame": frame,
                    "end_frame": frame,
                    "start_time_s": time_s,
                    "end_time_s": time_s,
                    "frames": 1,
                }
        else:
            if current is not None:
                intervals.append(current)
                current = None

    if current is not None:
        intervals.append(current)
    return intervals


def _transition_ball_stats(frame_df, start_frame, end_frame):
    """Inclusive open interval (start_frame, end_frame) i.e. frames strictly between."""
    if end_frame <= start_frame + 1:
        return {"n": 0, "missing": 0, "detected": 0, "interpolated": 0, "missing_ratio": 0.0}

    mid = frame_df[
        (frame_df["frame"] > start_frame) & (frame_df["frame"] < end_frame)
    ]
    n = int(len(mid))
    if n == 0:
        return {"n": 0, "missing": 0, "detected": 0, "interpolated": 0, "missing_ratio": 0.0}
    missing = int((mid["ball_source"] == "missing").sum())
    detected = int((mid["ball_source"] == "detected").sum())
    interpolated = int((mid["ball_source"] == "interpolated").sum())
    return {
        "n": n,
        "missing": missing,
        "detected": detected,
        "interpolated": interpolated,
        "missing_ratio": missing / n,
    }


def _pass_confidence(transition_frames, passer_frames, missing_ratio):
    score = 0.40
    if transition_frames <= 10:
        score += 0.25
    elif transition_frames <= 20:
        score += 0.15
    else:
        score += 0.05
    score += 0.20 * max(0.0, 1.0 - missing_ratio)
    if passer_frames >= 15:
        score += 0.15
    elif passer_frames >= PASS_MIN_POSSESSION_FRAMES:
        score += 0.08
    return round(min(1.0, score), 3)


def classify_transition(prev, nxt, teams, ball_stats):
    passer = prev["stable_id"]
    receiver = nxt["stable_id"]
    transition_frames = nxt["start_frame"] - prev["end_frame"] - 1
    if transition_frames < 0:
        transition_frames = 0

    team_a = teams.get(passer)
    team_b = teams.get(receiver)

    if passer == receiver:
        return "rejected", "same_stable_id", None

    if prev["frames"] < PASS_MIN_POSSESSION_FRAMES:
        return "rejected", "passer_possession_too_short", None

    if nxt["frames"] < PASS_MIN_POSSESSION_FRAMES:
        return "rejected", "receiver_possession_too_short", None

    if transition_frames > PASS_MAX_TRANSITION_FRAMES:
        return "rejected", "transition_too_long", None

    if ball_stats["n"] > 0 and ball_stats["missing_ratio"] > PASS_MAX_MISSING_BALL_RATIO:
        return "rejected", "ball_missing_during_transition", None

    if team_a not in VALID_TEAMS or team_b not in VALID_TEAMS:
        return "unknown_transition", "missing_or_invalid_team", None

    if team_a != team_b:
        return "unknown_transition", "cross_team", None

    confidence = _pass_confidence(
        transition_frames,
        prev["frames"],
        ball_stats["missing_ratio"],
    )
    return "completed_pass", "same_team_confirmed_possession", confidence


def detect_passes(frame_state_csv, teams_csv, fps):
    frame_df = pd.read_csv(frame_state_csv)
    teams = _load_teams(teams_csv)
    intervals = _confirmed_intervals(frame_df)

    validation = []
    passes = []
    event_id = 1
    counts = {
        "confirmed_intervals": len(intervals),
        "transitions": 0,
        "completed_passes": 0,
        "same_team_transitions": 0,
        "cross_team_transitions": 0,
        "unknown_transitions": 0,
        "rejected_transitions": 0,
    }

    for i in range(len(intervals) - 1):
        prev = intervals[i]
        nxt = intervals[i + 1]
        counts["transitions"] += 1
        transition_frames = max(0, nxt["start_frame"] - prev["end_frame"] - 1)
        ball_stats = _transition_ball_stats(
            frame_df, prev["end_frame"], nxt["start_frame"]
        )
        team_a = teams.get(prev["stable_id"])
        team_b = teams.get(nxt["stable_id"])
        if team_a in VALID_TEAMS and team_b in VALID_TEAMS:
            if team_a == team_b:
                counts["same_team_transitions"] += 1
            else:
                counts["cross_team_transitions"] += 1

        decision, reason, confidence = classify_transition(
            prev, nxt, teams, ball_stats
        )
        rec = {
            "event_id": event_id if decision == "completed_pass" else "",
            "decision": decision,
            "reason": reason,
            "frame": nxt["start_frame"],
            "time_s": round(nxt["start_time_s"], 4) if nxt["start_time_s"] is not None else "",
            "passer_stable_id": prev["stable_id"],
            "receiver_stable_id": nxt["stable_id"],
            "passer_team_id": team_a or "",
            "receiver_team_id": team_b or "",
            "team_id": team_a if decision == "completed_pass" else "",
            "transition_frames": transition_frames,
            "passer_possession_frames": prev["frames"],
            "receiver_possession_frames": nxt["frames"],
            "ball_missing_ratio": round(ball_stats["missing_ratio"], 3),
            "confidence": confidence if confidence is not None else "",
        }
        validation.append(rec)

        if decision == "completed_pass":
            counts["completed_passes"] += 1
            passes.append({
                "event_id": event_id,
                "frame": rec["frame"],
                "time_s": rec["time_s"],
                "passer_stable_id": rec["passer_stable_id"],
                "receiver_stable_id": rec["receiver_stable_id"],
                "team_id": rec["team_id"],
                "transition_frames": transition_frames,
                "passer_possession_frames": prev["frames"],
                "confidence": confidence,
                "reason": reason,
            })
            event_id += 1
        elif decision == "unknown_transition":
            counts["unknown_transitions"] += 1
        else:
            counts["rejected_transitions"] += 1

    return intervals, passes, validation, counts, fps


def _write_csv(path, rows, fieldnames):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_team_pass_stats(passes, output_path):
    totals = {}
    for row in passes:
        team = row["team_id"]
        totals[team] = totals.get(team, 0) + 1
    rows = [
        {"team_id": team, "completed_passes": count}
        for team, count in sorted(totals.items())
    ]
    if not rows:
        rows = [{"team_id": "team_a", "completed_passes": 0}, {"team_id": "team_b", "completed_passes": 0}]
    return _write_csv(
        output_path,
        rows,
        ["team_id", "completed_passes"],
    )


def write_player_pass_stats(passes, teams, output_path):
    totals = {}
    for row in passes:
        sid = row["passer_stable_id"]
        totals[sid] = totals.get(sid, 0) + 1
    rows = []
    for sid, count in sorted(totals.items()):
        rows.append({
            "stable_id": sid,
            "team_id": teams.get(sid, ""),
            "successful_passes": count,
            "note": "stable_id_level_mvp_not_unique_player",
        })
    return _write_csv(
        output_path,
        rows,
        ["stable_id", "team_id", "successful_passes", "note"],
    )


def run_pass_detection(
    frame_state_csv,
    teams_csv,
    video_path,
    suffix="",
):
    EVENTS_OUTPUT.mkdir(parents=True, exist_ok=True)
    ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)
    fps = _video_fps(video_path)
    tag = f"_{suffix}" if suffix else ""

    intervals, passes, validation, counts, fps = detect_passes(
        frame_state_csv, teams_csv, fps
    )
    teams = _load_teams(teams_csv)

    passes_path = EVENTS_OUTPUT / f"passes{tag}.csv"
    validation_path = EVENTS_OUTPUT / f"pass_validation{tag}.csv"
    team_stats_path = ANALYTICS_DIR / f"team_event_stats{tag}.csv"
    player_stats_path = ANALYTICS_DIR / f"player_pass_stats{tag}.csv"

    _write_csv(
        passes_path,
        passes,
        [
            "event_id",
            "frame",
            "time_s",
            "passer_stable_id",
            "receiver_stable_id",
            "team_id",
            "transition_frames",
            "passer_possession_frames",
            "confidence",
            "reason",
        ],
    )
    _write_csv(
        validation_path,
        validation,
        [
            "event_id",
            "decision",
            "reason",
            "frame",
            "time_s",
            "passer_stable_id",
            "receiver_stable_id",
            "passer_team_id",
            "receiver_team_id",
            "team_id",
            "transition_frames",
            "passer_possession_frames",
            "receiver_possession_frames",
            "ball_missing_ratio",
            "confidence",
        ],
    )
    write_team_pass_stats(passes, team_stats_path)
    write_player_pass_stats(passes, teams, player_stats_path)

    print("Pass detection (MVP, stable_id-level):")
    print(f"  FPS                        : {fps:.4f}")
    print(f"  max transition frames      : {PASS_MAX_TRANSITION_FRAMES}")
    print(f"  min possession frames      : {PASS_MIN_POSSESSION_FRAMES}")
    print(f"  confirmed intervals        : {counts['confirmed_intervals']}")
    print(f"  possession transitions     : {counts['transitions']}")
    print(f"  same-team transitions      : {counts['same_team_transitions']}")
    print(f"  cross-team transitions     : {counts['cross_team_transitions']}")
    print(f"  completed passes           : {counts['completed_passes']}")
    print(f"  unknown transitions        : {counts['unknown_transitions']}")
    print(f"  rejected transitions       : {counts['rejected_transitions']}")
    print(f"  passes CSV                 : {passes_path}")
    print(f"  validation CSV             : {validation_path}")
    print(f"  team stats                 : {team_stats_path}")
    print(f"  player pass stats          : {player_stats_path}")

    return {
        "counts": counts,
        "passes": passes,
        "validation": validation,
        "passes_csv": passes_path,
        "validation_csv": validation_path,
        "team_stats_csv": team_stats_path,
        "player_stats_csv": player_stats_path,
        "fps": fps,
    }
