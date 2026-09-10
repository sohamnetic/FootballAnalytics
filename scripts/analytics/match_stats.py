"""
Product data layer: unify MVP event CSVs into one match-stats payload.

Does not modify tracking, identity, ball detection, or event engines.
stable_id is an MVP identity, not a guaranteed real-world player.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import cv2
import pandas as pd

from config.config import OUTPUT_DIR, RAW_VIDEO
from scripts.analytics.events.passes import VALID_TEAMS, _confirmed_intervals, _load_teams

ANALYTICS_DIR = OUTPUT_DIR / "analytics"
PIPELINE_VERSION = "mvp-product-data-v1"
IDENTITY_QUALITY = "MVP_FRAGMENTED"

KNOWN_LIMITATIONS = [
    "stable_id is not a unique real-world player; identity is fragmented across ByteTrack gaps.",
    "Team assignment is jersey-colour clustering in camera pixels, not official team sheets.",
    "Pass accuracy is null: completed passes exist, but attempted-pass is not a defensible MVP definition.",
    "Shot and goal geometry is manually configured in camera pixels, not metres or homography.",
    "False-positive goals are suppressed by design; missed shots/goals are expected.",
    "Interceptions and recoveries are conservative post-process labels, not broadcast events.",
    "Possession percentage uses confirmed possession duration over clip length; loose/candidate/unknown is excluded from team totals.",
]


def _video_fps(video_path):
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    if fps is None or fps <= 0:
        raise RuntimeError(f"Cannot read FPS from {video_path}")
    return float(fps)


def _read_csv_or_empty(path, columns=None):
    path = Path(path) if path else None
    if path is None or not path.exists():
        return pd.DataFrame(columns=columns or [])
    df = pd.read_csv(path)
    if df is None or df.empty:
        return pd.DataFrame(columns=list(df.columns) if df is not None else (columns or []))
    return df


def _as_bool(value):
    if isinstance(value, bool):
        return value
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return False
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "t"}


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


def _ratio_or_null(numerator, denominator):
    if not denominator:
        return None
    return round(100.0 * numerator / denominator, 2)


def _empty_player(stable_id, team_id):
    return {
        "stable_id": stable_id,
        "team_id": team_id,
        "goals": 0,
        "shots": 0,
        "shots_on_target": 0,
        "shot_accuracy": None,
        "shot_conversion_rate": None,
        "successful_passes": 0,
        "pass_accuracy": None,
        "interceptions": 0,
        "ball_recoveries": 0,
        "ball_possession_time_seconds": 0.0,
    }


def _empty_team():
    return {
        "possession_percentage": 0.0,
        "possession_seconds": 0.0,
        "goals": 0,
        "shots": 0,
        "shots_on_target": 0,
        "completed_passes": 0,
        "pass_accuracy": None,
        "interceptions": 0,
        "ball_recoveries": 0,
    }


def _clip_duration_s(frame_df, fps, start_time_s, duration_s):
    if duration_s is not None:
        return float(duration_s)
    if frame_df is None or frame_df.empty:
        return 0.0
    t0 = float(frame_df["time_s"].min())
    t1 = float(frame_df["time_s"].max())
    return max(0.0, t1 - t0 + (1.0 / fps))


def _possession_seconds(frame_df, fps):
    """
    Confirmed possession duration from frame count / actual FPS.
    Also returns interval/transition counts from confirmed runs.
    """
    by_player = defaultdict(float)
    by_team_frames = defaultdict(int)
    state_frames = defaultdict(int)
    frame_period = 1.0 / fps

    if frame_df is None or frame_df.empty:
        return by_player, by_team_frames, state_frames, 0, 0

    for _, row in frame_df.iterrows():
        state = str(row.get("possession_state", "")).strip().lower()
        state_frames[state] += 1

    intervals = _confirmed_intervals(frame_df)
    for interval in intervals:
        sid = interval["stable_id"]
        seconds = interval["frames"] * frame_period
        by_player[sid] += seconds
        by_team_frames[sid] += interval["frames"]

    transitions = max(0, len(intervals) - 1)
    return by_player, by_team_frames, state_frames, len(intervals), transitions


def _dedupe_events(df, id_col="event_id"):
    if df is None or df.empty:
        return df
    if id_col not in df.columns:
        return df.drop_duplicates()
    return df.drop_duplicates(subset=[id_col], keep="first")


def build_match_stats(
    *,
    frame_state_csv,
    teams_csv,
    passes_csv,
    interceptions_csv,
    recoveries_csv,
    shots_csv,
    video_path,
    start_time_s=200,
    duration_s=40,
    identity_audit_csv=None,
):
    fps = _video_fps(video_path)
    teams = _load_teams(teams_csv)
    teams_df = _read_csv_or_empty(teams_csv)
    frame_df = _read_csv_or_empty(frame_state_csv)
    passes_df = _dedupe_events(_read_csv_or_empty(passes_csv))
    intercepts_df = _dedupe_events(_read_csv_or_empty(interceptions_csv))
    recoveries_df = _dedupe_events(_read_csv_or_empty(recoveries_csv))
    shots_df = _dedupe_events(_read_csv_or_empty(shots_csv))

    inconsistencies = []
    valid_players = {
        sid: team for sid, team in teams.items() if team in VALID_TEAMS
    }

    team_stats = {"team_a": _empty_team(), "team_b": _empty_team()}
    players = {sid: _empty_player(sid, team) for sid, team in sorted(valid_players.items())}

    clip_s = _clip_duration_s(frame_df, fps, start_time_s, duration_s)
    poss_by_player, _, state_frames, n_intervals, n_transitions = _possession_seconds(
        frame_df, fps
    )

    unknown_poss_s = 0.0
    for sid, seconds in poss_by_player.items():
        team = teams.get(sid)
        if sid in players:
            players[sid]["ball_possession_time_seconds"] = round(seconds, 4)
            team_stats[players[sid]["team_id"]]["possession_seconds"] += seconds
        else:
            unknown_poss_s += seconds
            if team not in VALID_TEAMS:
                inconsistencies.append(
                    f"confirmed possession on stable_id {sid} with team={team or 'missing'} excluded from team_a/team_b"
                )

    for team_id, block in team_stats.items():
        if clip_s > 0:
            block["possession_percentage"] = round(
                100.0 * block["possession_seconds"] / clip_s, 2
            )
        else:
            block["possession_percentage"] = None
        block["possession_seconds"] = round(block["possession_seconds"], 4)

    # Passes: completed only, attributed to passer
    if not passes_df.empty:
        for _, row in passes_df.iterrows():
            passer = _int_or_none(row.get("passer_stable_id"))
            team = str(row.get("team_id", "")).strip().lower()
            if passer in players and team == players[passer]["team_id"]:
                players[passer]["successful_passes"] += 1
                team_stats[team]["completed_passes"] += 1
            else:
                inconsistencies.append(
                    f"pass event_id={row.get('event_id')} passer={passer} team={team} not attributed"
                )

    if not intercepts_df.empty:
        for _, row in intercepts_df.iterrows():
            sid = _int_or_none(row.get("interceptor_stable_id"))
            team = str(row.get("team_id", "")).strip().lower()
            if sid in players and team == players[sid]["team_id"]:
                players[sid]["interceptions"] += 1
                team_stats[team]["interceptions"] += 1
            else:
                inconsistencies.append(
                    f"interception event_id={row.get('event_id')} interceptor={sid} team={team} not attributed"
                )

    if not recoveries_df.empty:
        for _, row in recoveries_df.iterrows():
            sid = _int_or_none(row.get("player_stable_id"))
            team = str(row.get("team_id", "")).strip().lower()
            if sid in players and team == players[sid]["team_id"]:
                players[sid]["ball_recoveries"] += 1
                team_stats[team]["ball_recoveries"] += 1
            else:
                inconsistencies.append(
                    f"recovery event_id={row.get('event_id')} player={sid} team={team} not attributed"
                )

    if not shots_df.empty:
        for _, row in shots_df.iterrows():
            sid = _int_or_none(row.get("shooter_stable_id"))
            team = str(row.get("team_id", "")).strip().lower()
            on_target = _as_bool(row.get("on_target"))
            is_goal = _as_bool(row.get("goal"))
            if is_goal and not on_target:
                inconsistencies.append(
                    f"shot event_id={row.get('event_id')} marked goal without on_target"
                )
                is_goal = False
            if sid in players and team == players[sid]["team_id"]:
                players[sid]["shots"] += 1
                team_stats[team]["shots"] += 1
                if on_target:
                    players[sid]["shots_on_target"] += 1
                    team_stats[team]["shots_on_target"] += 1
                if is_goal:
                    players[sid]["goals"] += 1
                    team_stats[team]["goals"] += 1
            else:
                inconsistencies.append(
                    f"shot event_id={row.get('event_id')} shooter={sid} team={team} not attributed"
                )

    for player in players.values():
        player["shot_accuracy"] = _ratio_or_null(player["shots_on_target"], player["shots"])
        player["shot_conversion_rate"] = _ratio_or_null(player["goals"], player["shots"])
        player["pass_accuracy"] = None
        player["ball_possession_time_seconds"] = round(
            player["ball_possession_time_seconds"], 4
        )

    player_list = list(players.values())

    identity_ids = None
    if identity_audit_csv and Path(identity_audit_csv).exists():
        ident = pd.read_csv(identity_audit_csv)
        if "stable_id" in ident.columns:
            identity_ids = int(ident["stable_id"].nunique())

    team_id_counts = {}
    if not teams_df.empty and "team_id" in teams_df.columns:
        team_id_counts = {
            str(k): int(v) for k, v in teams_df["team_id"].astype(str).value_counts().items()
        }

    confirmed_s = sum(poss_by_player.values())
    event_summary = {
        "possession_intervals": n_intervals,
        "possession_transitions": n_transitions,
        "completed_passes": int(len(passes_df)) if passes_df is not None else 0,
        "interceptions": int(len(intercepts_df)) if intercepts_df is not None else 0,
        "recoveries": int(len(recoveries_df)) if recoveries_df is not None else 0,
        "shots": int(len(shots_df)) if shots_df is not None else 0,
        "shots_on_target": int(
            shots_df["on_target"].map(_as_bool).sum()
        ) if shots_df is not None and not shots_df.empty and "on_target" in shots_df.columns else 0,
        "goals": int(
            shots_df["goal"].map(_as_bool).sum()
        ) if shots_df is not None and not shots_df.empty and "goal" in shots_df.columns else 0,
    }

    payload = {
        "match": {
            "video": str(Path(video_path)),
            "start_time_s": float(start_time_s) if start_time_s is not None else None,
            "duration_s": float(duration_s) if duration_s is not None else round(clip_s, 4),
            "fps": round(fps, 4),
            "clip_duration_used_s": round(clip_s, 4),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": PIPELINE_VERSION,
        "identity_quality": IDENTITY_QUALITY,
        "data_quality": {
            "stable_ids": int(teams_df["stable_id"].nunique()) if not teams_df.empty else len(teams),
            "identity_audit_stable_ids": identity_ids,
            "valid_team_players": len(players),
            "team_assignment_counts": team_id_counts,
            "estimated_visible_players": "~10-16",
            "identity_fragmentation": True,
            "team_assignment_uncertainty": True,
            "goal_geometry_manual": True,
            "pass_attempts_available": False,
            "possession_confirmed_seconds": round(confirmed_s, 4),
            "possession_unknown_or_unassigned_seconds": round(unknown_poss_s, 4),
            "possession_state_frames": dict(state_frames),
        },
        "event_summary": event_summary,
        "teams": team_stats,
        "players": player_list,
        "known_limitations": KNOWN_LIMITATIONS,
        "inconsistencies": inconsistencies,
    }

    validation = validate_match_stats(payload)
    payload["validation"] = validation
    return payload


def validate_match_stats(payload):
    teams = payload["teams"]
    players = payload["players"]
    summary = payload["event_summary"]
    checks = {}

    def sum_field(name):
        return sum(p[name] for p in players)

    checks["team_goals_eq_player_goals"] = (
        teams["team_a"]["goals"] + teams["team_b"]["goals"] == sum_field("goals")
        == summary["goals"]
    )
    checks["team_shots_eq_player_shots"] = (
        teams["team_a"]["shots"] + teams["team_b"]["shots"] == sum_field("shots")
        == summary["shots"]
    )
    checks["team_sot_eq_player_sot"] = (
        teams["team_a"]["shots_on_target"] + teams["team_b"]["shots_on_target"]
        == sum_field("shots_on_target")
        == summary["shots_on_target"]
    )
    checks["team_passes_eq_player_passes"] = (
        teams["team_a"]["completed_passes"] + teams["team_b"]["completed_passes"]
        == sum_field("successful_passes")
        == summary["completed_passes"]
    )
    checks["team_intercepts_eq_player_intercepts"] = (
        teams["team_a"]["interceptions"] + teams["team_b"]["interceptions"]
        == sum_field("interceptions")
        == summary["interceptions"]
    )
    checks["team_recoveries_eq_player_recoveries"] = (
        teams["team_a"]["ball_recoveries"] + teams["team_b"]["ball_recoveries"]
        == sum_field("ball_recoveries")
        == summary["recoveries"]
    )

    poss_sum = (
        teams["team_a"]["possession_percentage"] + teams["team_b"]["possession_percentage"]
    )
    checks["possession_percent_not_forced_to_100"] = poss_sum <= 100.01
    checks["possession_percent_sum"] = round(poss_sum, 2)
    checks["no_unknown_team_in_team_blocks"] = set(teams.keys()) == {"team_a", "team_b"}
    checks["no_duplicate_player_ids"] = len(players) == len({p["stable_id"] for p in players})
    checks["all_players_have_valid_team"] = all(p["team_id"] in VALID_TEAMS for p in players)
    checks["null_shot_metrics_when_zero_shots"] = all(
        (p["shot_accuracy"] is None and p["shot_conversion_rate"] is None)
        if p["shots"] == 0
        else (p["shot_accuracy"] is not None and p["shot_conversion_rate"] is not None)
        for p in players
    )
    checks["pass_accuracy_always_null"] = all(p["pass_accuracy"] is None for p in players)
    checks["team_pass_accuracy_null"] = all(
        teams[t]["pass_accuracy"] is None for t in ("team_a", "team_b")
    )
    checks["no_ball_as_player"] = all(p["stable_id"] is not None for p in players)
    checks["ok"] = all(
        v is True
        for k, v in checks.items()
        if k != "possession_percent_sum"
    )
    return checks


def _write_debug_csv(payload, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for team_id, block in payload["teams"].items():
        rows.append({
            "entity": "team",
            "team_id": team_id,
            "stable_id": "",
            "possession_percentage": block["possession_percentage"],
            "possession_seconds": block["possession_seconds"],
            "goals": block["goals"],
            "shots": block["shots"],
            "shots_on_target": block["shots_on_target"],
            "shot_accuracy": "",
            "shot_conversion_rate": "",
            "completed_passes": block["completed_passes"],
            "successful_passes": block["completed_passes"],
            "pass_accuracy": "",
            "interceptions": block["interceptions"],
            "ball_recoveries": block["ball_recoveries"],
            "ball_possession_time_seconds": block["possession_seconds"],
        })
    for p in payload["players"]:
        rows.append({
            "entity": "player",
            "team_id": p["team_id"],
            "stable_id": p["stable_id"],
            "possession_percentage": "",
            "possession_seconds": p["ball_possession_time_seconds"],
            "goals": p["goals"],
            "shots": p["shots"],
            "shots_on_target": p["shots_on_target"],
            "shot_accuracy": "" if p["shot_accuracy"] is None else p["shot_accuracy"],
            "shot_conversion_rate": "" if p["shot_conversion_rate"] is None else p["shot_conversion_rate"],
            "completed_passes": p["successful_passes"],
            "successful_passes": p["successful_passes"],
            "pass_accuracy": "",
            "interceptions": p["interceptions"],
            "ball_recoveries": p["ball_recoveries"],
            "ball_possession_time_seconds": p["ball_possession_time_seconds"],
        })
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "entity",
                "team_id",
                "stable_id",
                "possession_percentage",
                "possession_seconds",
                "goals",
                "shots",
                "shots_on_target",
                "shot_accuracy",
                "shot_conversion_rate",
                "completed_passes",
                "successful_passes",
                "pass_accuracy",
                "interceptions",
                "ball_recoveries",
                "ball_possession_time_seconds",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def run_match_stats(
    *,
    frame_state_csv,
    teams_csv,
    passes_csv,
    interceptions_csv,
    recoveries_csv,
    shots_csv,
    video_path,
    suffix="",
    start_time_s=200,
    duration_s=40,
    identity_audit_csv=None,
):
    ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)
    tag = f"_{suffix}" if suffix else ""
    payload = build_match_stats(
        frame_state_csv=frame_state_csv,
        teams_csv=teams_csv,
        passes_csv=passes_csv,
        interceptions_csv=interceptions_csv,
        recoveries_csv=recoveries_csv,
        shots_csv=shots_csv,
        video_path=video_path,
        start_time_s=start_time_s,
        duration_s=duration_s,
        identity_audit_csv=identity_audit_csv,
    )
    json_path = ANALYTICS_DIR / f"match_stats{tag}.json"
    csv_path = ANALYTICS_DIR / f"match_stats{tag}.csv"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_debug_csv(payload, csv_path)

    teams = payload["teams"]
    print("Match stats (product data layer, no new CV):")
    print(f"  pipeline_version               : {payload['pipeline_version']}")
    print(f"  identity_quality               : {payload['identity_quality']}")
    print(f"  FPS                            : {payload['match']['fps']}")
    print(f"  event_summary                  : {payload['event_summary']}")
    print(f"  team_a possession %            : {teams['team_a']['possession_percentage']}")
    print(f"  team_b possession %            : {teams['team_b']['possession_percentage']}")
    print(f"  validation.ok                  : {payload['validation']['ok']}")
    print(f"  JSON                           : {json_path}")
    print(f"  CSV                            : {csv_path}")

    return {
        "json": json_path,
        "csv": csv_path,
        "payload": payload,
    }
