"""
MVP interceptions and ball recoveries.

Post-process of confirmed possession intervals + team assignment.
Does not modify possession.py, passes.py, or frame_state.csv.

Precedence for a consecutive confirmed-possession pair:
  1. same-team pass-quality → skip (already handled by passes.py)
  2. cross-team, short, ball evidence → interception
  3. loose/unknown gap, valid new owner → recovery
  4. otherwise unknown_turnover or rejected

stable_id is an MVP identity, not a guaranteed real player.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from config.config import (
    EVENTS_OUTPUT,
    INTERCEPTION_MAX_TRANSITION_FRAMES,
    OUTPUT_DIR,
    PASS_MAX_MISSING_BALL_RATIO,
    PASS_MIN_POSSESSION_FRAMES,
    RECOVERY_MAX_TRANSITION_FRAMES,
)

from scripts.analytics.events.passes import (
    VALID_TEAMS,
    _confirmed_intervals,
    _load_teams,
    _transition_ball_stats,
    _video_fps,
    classify_transition,
)

ANALYTICS_DIR = OUTPUT_DIR / "analytics"
LOOSE_STATES = {"loose", "unknown"}


def _gap_state_stats(frame_df, start_frame, end_frame):
    """Frames strictly between two confirmed intervals."""
    if end_frame <= start_frame + 1:
        return {"n": 0, "loose_or_unknown": 0, "loose_ratio": 0.0}
    mid = frame_df[
        (frame_df["frame"] > start_frame) & (frame_df["frame"] < end_frame)
    ]
    n = int(len(mid))
    if n == 0:
        return {"n": 0, "loose_or_unknown": 0, "loose_ratio": 0.0}
    states = mid["possession_state"].astype(str).str.strip().str.lower()
    loose = int(states.isin(LOOSE_STATES).sum())
    return {"n": n, "loose_or_unknown": loose, "loose_ratio": loose / n}


def _event_confidence(transition_frames, owner_frames, missing_ratio, loose_ratio=0.0):
    score = 0.35
    if transition_frames <= 10:
        score += 0.25
    elif transition_frames <= 20:
        score += 0.15
    else:
        score += 0.05
    score += 0.20 * max(0.0, 1.0 - missing_ratio)
    score += 0.10 * min(1.0, loose_ratio)
    if owner_frames >= 15:
        score += 0.10
    elif owner_frames >= PASS_MIN_POSSESSION_FRAMES:
        score += 0.05
    return round(min(1.0, score), 3)


def _write_csv(path, rows, fieldnames):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def classify_turnover_pair(prev, nxt, teams, ball_stats, gap_stats):
    """
    Classify one confirmed-interval pair. Never emits a completed_pass event.
    """
    passer = prev["stable_id"]
    receiver = nxt["stable_id"]
    transition_frames = max(0, nxt["start_frame"] - prev["end_frame"] - 1)
    prev_team = teams.get(passer)
    next_team = teams.get(receiver)

    pass_decision, pass_reason, pass_conf = classify_transition(
        prev, nxt, teams, ball_stats
    )
    if pass_decision == "completed_pass":
        return {
            "classification": "skipped_pass_domain",
            "reason": "same_team_pass_candidate",
            "confidence": pass_conf,
        }

    if passer == receiver:
        return {
            "classification": "rejected",
            "reason": "same_stable_id",
            "confidence": "",
        }

    if prev["frames"] < PASS_MIN_POSSESSION_FRAMES:
        return {
            "classification": "rejected",
            "reason": "previous_possession_too_short",
            "confidence": "",
        }

    if nxt["frames"] < PASS_MIN_POSSESSION_FRAMES:
        return {
            "classification": "rejected",
            "reason": "new_possession_too_short",
            "confidence": "",
        }

    if ball_stats["n"] > 0 and ball_stats["missing_ratio"] > PASS_MAX_MISSING_BALL_RATIO:
        return {
            "classification": "rejected",
            "reason": "ball_missing_during_transition",
            "confidence": "",
        }

    # Cross-team: interception candidate
    both_valid = prev_team in VALID_TEAMS and next_team in VALID_TEAMS
    if both_valid and prev_team != next_team:
        if transition_frames > INTERCEPTION_MAX_TRANSITION_FRAMES:
            return {
                "classification": "unknown_turnover",
                "reason": "cross_team_transition_too_long",
                "confidence": "",
            }
        conf = _event_confidence(
            transition_frames,
            nxt["frames"],
            ball_stats["missing_ratio"],
            gap_stats["loose_ratio"],
        )
        return {
            "classification": "interception",
            "reason": "cross_team_confirmed_possession",
            "confidence": conf,
        }

    # Loose/unknown gap: recovery candidate (not a classified pass or intercept)
    if next_team in VALID_TEAMS and transition_frames <= RECOVERY_MAX_TRANSITION_FRAMES:
        mostly_loose = gap_stats["n"] == 0 or gap_stats["loose_ratio"] >= 0.5
        prev_unreliable = prev_team not in VALID_TEAMS
        if mostly_loose and (prev_unreliable or gap_stats["loose_ratio"] >= 0.5):
            # Direct cross-team with valid teams already handled. Same-team
            # non-pass (e.g. unknown_transition missing team on one side) can recover.
            if both_valid and prev_team == next_team:
                return {
                    "classification": "unknown_turnover",
                    "reason": "same_team_but_not_a_pass",
                    "confidence": "",
                }
            conf = _event_confidence(
                transition_frames,
                nxt["frames"],
                ball_stats["missing_ratio"],
                gap_stats["loose_ratio"],
            )
            return {
                "classification": "recovery",
                "reason": "loose_or_unknown_then_confirmed",
                "confidence": conf,
            }

    if transition_frames > INTERCEPTION_MAX_TRANSITION_FRAMES:
        return {
            "classification": "rejected",
            "reason": "transition_too_long",
            "confidence": "",
        }

    if next_team not in VALID_TEAMS or prev_team not in VALID_TEAMS:
        return {
            "classification": "unknown_turnover",
            "reason": "missing_or_invalid_team",
            "confidence": "",
        }

    return {
        "classification": "unknown_turnover",
        "reason": "insufficient_evidence",
        "confidence": "",
    }


def detect_turnovers(frame_state_csv, teams_csv, fps):
    frame_df = pd.read_csv(frame_state_csv)
    teams = _load_teams(teams_csv)
    intervals = _confirmed_intervals(frame_df)

    validation = []
    interceptions = []
    recoveries = []
    intercept_id = 1
    recovery_id = 1
    counts = {
        "confirmed_intervals": len(intervals),
        "turnover_candidates": 0,
        "cross_team_transitions": 0,
        "interceptions": 0,
        "recoveries": 0,
        "unknown_turnovers": 0,
        "rejected": 0,
        "skipped_pass_domain": 0,
    }

    for i in range(len(intervals) - 1):
        prev = intervals[i]
        nxt = intervals[i + 1]
        counts["turnover_candidates"] += 1
        transition_frames = max(0, nxt["start_frame"] - prev["end_frame"] - 1)
        ball_stats = _transition_ball_stats(
            frame_df, prev["end_frame"], nxt["start_frame"]
        )
        gap_stats = _gap_state_stats(
            frame_df, prev["end_frame"], nxt["start_frame"]
        )
        prev_team = teams.get(prev["stable_id"])
        next_team = teams.get(nxt["stable_id"])
        if (
            prev_team in VALID_TEAMS
            and next_team in VALID_TEAMS
            and prev_team != next_team
        ):
            counts["cross_team_transitions"] += 1

        result = classify_turnover_pair(
            prev, nxt, teams, ball_stats, gap_stats
        )
        classification = result["classification"]
        rec = {
            "frame": nxt["start_frame"],
            "time_s": round(nxt["start_time_s"], 4) if nxt["start_time_s"] is not None else "",
            "previous_owner_stable_id": prev["stable_id"],
            "previous_team_id": prev_team or "",
            "new_owner_stable_id": nxt["stable_id"],
            "new_team_id": next_team or "",
            "transition_frames": transition_frames,
            "previous_possession_frames": prev["frames"],
            "new_possession_frames": nxt["frames"],
            "ball_missing_ratio": round(ball_stats["missing_ratio"], 3),
            "loose_ratio": round(gap_stats["loose_ratio"], 3),
            "classification": classification,
            "confidence": result["confidence"] if result["confidence"] != "" else "",
            "reason": result["reason"],
        }

        if classification == "interception":
            rec["event_id"] = intercept_id
            interceptions.append({
                "event_id": intercept_id,
                "frame": rec["frame"],
                "time_s": rec["time_s"],
                "interceptor_stable_id": nxt["stable_id"],
                "opponent_stable_id": prev["stable_id"],
                "team_id": next_team,
                "opponent_team_id": prev_team,
                "transition_frames": transition_frames,
                "confidence": result["confidence"],
                "reason": result["reason"],
            })
            intercept_id += 1
            counts["interceptions"] += 1
        elif classification == "recovery":
            rec["event_id"] = recovery_id
            recoveries.append({
                "event_id": recovery_id,
                "frame": rec["frame"],
                "player_stable_id": nxt["stable_id"],
                "team_id": next_team,
                "transition_frames": transition_frames,
                "confidence": result["confidence"],
                "reason": result["reason"],
            })
            recovery_id += 1
            counts["recoveries"] += 1
        elif classification == "unknown_turnover":
            rec["event_id"] = ""
            counts["unknown_turnovers"] += 1
        elif classification == "skipped_pass_domain":
            rec["event_id"] = ""
            counts["skipped_pass_domain"] += 1
        else:
            rec["event_id"] = ""
            counts["rejected"] += 1

        validation.append(rec)

    return interceptions, recoveries, validation, counts, teams, fps


def _write_defensive_stats(interceptions, recoveries, teams, suffix):
    team_ids = sorted(VALID_TEAMS)
    team_int = {t: 0 for t in team_ids}
    team_rec = {t: 0 for t in team_ids}
    player_int = {}
    player_rec = {}

    for row in interceptions:
        team_int[row["team_id"]] = team_int.get(row["team_id"], 0) + 1
        sid = row["interceptor_stable_id"]
        player_int[sid] = player_int.get(sid, 0) + 1
    for row in recoveries:
        team_rec[row["team_id"]] = team_rec.get(row["team_id"], 0) + 1
        sid = row["player_stable_id"]
        player_rec[sid] = player_rec.get(sid, 0) + 1

    team_rows = [
        {
            "team_id": team,
            "interceptions": team_int.get(team, 0),
            "ball_recoveries": team_rec.get(team, 0),
        }
        for team in team_ids
    ]
    sids = sorted(set(player_int) | set(player_rec))
    player_rows = [
        {
            "stable_id": sid,
            "team_id": teams.get(sid, ""),
            "interceptions": player_int.get(sid, 0),
            "ball_recoveries": player_rec.get(sid, 0),
            "note": "stable_id_level_mvp_not_unique_player",
        }
        for sid in sids
    ]

    tag = f"_{suffix}" if suffix else ""
    team_path = ANALYTICS_DIR / f"team_defensive_event_stats{tag}.csv"
    player_path = ANALYTICS_DIR / f"player_defensive_event_stats{tag}.csv"
    _write_csv(
        team_path,
        team_rows,
        ["team_id", "interceptions", "ball_recoveries"],
    )
    _write_csv(
        player_path,
        player_rows,
        ["stable_id", "team_id", "interceptions", "ball_recoveries", "note"],
    )
    return team_path, player_path


def run_turnover_detection(frame_state_csv, teams_csv, video_path, suffix=""):
    EVENTS_OUTPUT.mkdir(parents=True, exist_ok=True)
    ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)
    fps = _video_fps(video_path)
    tag = f"_{suffix}" if suffix else ""

    interceptions, recoveries, validation, counts, teams, fps = detect_turnovers(
        frame_state_csv, teams_csv, fps
    )

    int_path = EVENTS_OUTPUT / f"interceptions{tag}.csv"
    rec_path = EVENTS_OUTPUT / f"recoveries{tag}.csv"
    val_path = EVENTS_OUTPUT / f"turnover_validation{tag}.csv"

    _write_csv(
        int_path,
        interceptions,
        [
            "event_id",
            "frame",
            "time_s",
            "interceptor_stable_id",
            "opponent_stable_id",
            "team_id",
            "opponent_team_id",
            "transition_frames",
            "confidence",
            "reason",
        ],
    )
    _write_csv(
        rec_path,
        recoveries,
        [
            "event_id",
            "frame",
            "player_stable_id",
            "team_id",
            "transition_frames",
            "confidence",
            "reason",
        ],
    )
    _write_csv(
        val_path,
        validation,
        [
            "event_id",
            "frame",
            "time_s",
            "previous_owner_stable_id",
            "previous_team_id",
            "new_owner_stable_id",
            "new_team_id",
            "transition_frames",
            "previous_possession_frames",
            "new_possession_frames",
            "ball_missing_ratio",
            "loose_ratio",
            "classification",
            "confidence",
            "reason",
        ],
    )
    team_path, player_path = _write_defensive_stats(
        interceptions, recoveries, teams, suffix
    )

    print("Turnover detection (MVP, stable_id-level):")
    print(f"  FPS                            : {fps:.4f}")
    print(f"  interception max gap           : {INTERCEPTION_MAX_TRANSITION_FRAMES}")
    print(f"  recovery max gap               : {RECOVERY_MAX_TRANSITION_FRAMES}")
    print(f"  confirmed intervals            : {counts['confirmed_intervals']}")
    print(f"  turnover candidates            : {counts['turnover_candidates']}")
    print(f"  cross-team transitions         : {counts['cross_team_transitions']}")
    print(f"  interceptions                  : {counts['interceptions']}")
    print(f"  recoveries                     : {counts['recoveries']}")
    print(f"  unknown turnovers              : {counts['unknown_turnovers']}")
    print(f"  rejected                       : {counts['rejected']}")
    print(f"  skipped (pass domain)          : {counts['skipped_pass_domain']}")
    print(f"  interceptions CSV              : {int_path}")
    print(f"  recoveries CSV                 : {rec_path}")
    print(f"  validation CSV                 : {val_path}")

    return {
        "counts": counts,
        "interceptions": interceptions,
        "recoveries": recoveries,
        "validation": validation,
        "interceptions_csv": int_path,
        "recoveries_csv": rec_path,
        "validation_csv": val_path,
        "team_stats_csv": team_path,
        "player_stats_csv": player_path,
        "fps": fps,
    }
