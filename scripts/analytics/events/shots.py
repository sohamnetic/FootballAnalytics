"""
MVP shot / shot-on-target / goal detection.

Post-process of confirmed possession intervals + frame_state ball track + teams.
Does not modify possession, passes, turnovers, tracking, or ball detection.

Goal geometry is camera-pixel boxes, not real-world metres.
stable_id is an MVP identity, not a guaranteed real player.
"""

from __future__ import annotations

import csv
from pathlib import Path

import cv2
import pandas as pd

from config.config import (
    EVENTS_OUTPUT,
    GOAL_ZONE_LEFT,
    GOAL_ZONE_RIGHT,
    OUTPUT_DIR,
    PASS_MAX_TRANSITION_FRAMES,
    SHOT_GOAL_APPROACH_WINDOW_FRAMES,
    SHOT_GOAL_INSIDE_FRAMES,
    SHOT_MAX_MISSING_BALL_RATIO,
    SHOT_MAX_TRANSITION_FRAMES,
    SHOT_MIN_BALL_MOVEMENT_PX,
    SHOT_MIN_GOAL_APPROACH_PX,
    SHOT_MIN_POSSESSION_FRAMES,
    SHOT_ON_TARGET_MAX_DIST_PX,
    SHOT_WRITE_VALIDATION_VIDEO,
    TEAM_DEFENDS_GOAL,
)

from scripts.analytics.events.passes import (
    VALID_TEAMS,
    _confirmed_intervals,
    _load_teams,
    _video_fps,
)

ANALYTICS_DIR = OUTPUT_DIR / "analytics"
OPPONENT_GOAL = {"team_a": "team_b", "team_b": "team_a"}


def _write_csv(path, rows, fieldnames):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _goal_zones():
    return {
        "left": tuple(int(v) for v in GOAL_ZONE_LEFT),
        "right": tuple(int(v) for v in GOAL_ZONE_RIGHT),
    }


def _rect_center(rect):
    x1, y1, x2, y2 = rect
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def _point_in_rect(x, y, rect):
    x1, y1, x2, y2 = rect
    return x1 <= x <= x2 and y1 <= y <= y2


def _point_rect_distance(x, y, rect):
    if _point_in_rect(x, y, rect):
        return 0.0
    x1, y1, x2, y2 = rect
    dx = max(x1 - x, 0.0, x - x2)
    dy = max(y1 - y, 0.0, y - y2)
    return float((dx * dx + dy * dy) ** 0.5)


def _segment_intersects_rect(x0, y0, x1, y1, rect):
    if _point_in_rect(x0, y0, rect) or _point_in_rect(x1, y1, rect):
        return True
    rx1, ry1, rx2, ry2 = rect
    edges = (
        (rx1, ry1, rx2, ry1),
        (rx2, ry1, rx2, ry2),
        (rx2, ry2, rx1, ry2),
        (rx1, ry2, rx1, ry1),
    )
    for ax, ay, bx, by in edges:
        if _segments_intersect(x0, y0, x1, y1, ax, ay, bx, by):
            return True
    return False


def _segments_intersect(x1, y1, x2, y2, x3, y3, x4, y4):
    def orient(ax, ay, bx, by, cx, cy):
        return (by - ay) * (cx - ax) - (bx - ax) * (cy - ay)

    o1 = orient(x1, y1, x2, y2, x3, y3)
    o2 = orient(x1, y1, x2, y2, x4, y4)
    o3 = orient(x3, y3, x4, y4, x1, y1)
    o4 = orient(x3, y3, x4, y4, x2, y2)
    return (o1 == 0 and o2 == 0) is False and (o1 * o2 <= 0) and (o3 * o4 <= 0)


def _target_goal_for_team(team_id):
    if team_id not in VALID_TEAMS:
        return None
    defended = TEAM_DEFENDS_GOAL.get(team_id)
    if defended not in ("left", "right"):
        return None
    return "right" if defended == "left" else "left"


def _ball_xy(row):
    source = str(row.get("ball_source", "")).strip().lower()
    if source == "missing":
        return None
    if pd.isna(row.get("ball_x")) or pd.isna(row.get("ball_y")):
        return None
    return float(row["ball_x"]), float(row["ball_y"]), source


def _window_rows(frame_df, start_frame, end_frame):
    """Inclusive frames after possession end, up to end_frame."""
    if end_frame <= start_frame:
        return frame_df.iloc[0:0]
    return frame_df[
        (frame_df["frame"] > start_frame) & (frame_df["frame"] <= end_frame)
    ].sort_values("frame")


def _trajectory(window, start_xy):
    points = []
    if start_xy is not None:
        points.append({
            "frame": None,
            "x": start_xy[0],
            "y": start_xy[1],
            "source": start_xy[2] if len(start_xy) > 2 else "detected",
        })
    n = 0
    missing = 0
    detected = 0
    interpolated = 0
    for _, row in window.iterrows():
        n += 1
        xy = _ball_xy(row)
        source = str(row.get("ball_source", "")).strip().lower()
        if source == "missing" or xy is None:
            missing += 1
            continue
        if source == "detected":
            detected += 1
        elif source == "interpolated":
            interpolated += 1
        points.append({
            "frame": int(row["frame"]),
            "x": xy[0],
            "y": xy[1],
            "source": source,
        })
    coverage = (detected + interpolated) / n if n else 0.0
    missing_ratio = missing / n if n else 1.0
    if len(points) < 2:
        return {
            "points": points,
            "n": n,
            "missing": missing,
            "detected": detected,
            "interpolated": interpolated,
            "coverage": coverage,
            "missing_ratio": missing_ratio,
            "start_x": None,
            "start_y": None,
            "end_x": None,
            "end_y": None,
            "movement_px": 0.0,
            "dx": 0.0,
            "dy": 0.0,
        }
    # Prefer first window point as start if we also prepended possession-end ball
    sx, sy = points[0]["x"], points[0]["y"]
    ex, ey = points[-1]["x"], points[-1]["y"]
    dx = ex - sx
    dy = ey - sy
    movement = float((dx * dx + dy * dy) ** 0.5)
    return {
        "points": points,
        "n": n,
        "missing": missing,
        "detected": detected,
        "interpolated": interpolated,
        "coverage": coverage,
        "missing_ratio": missing_ratio,
        "start_x": sx,
        "start_y": sy,
        "end_x": ex,
        "end_y": ey,
        "movement_px": movement,
        "dx": dx,
        "dy": dy,
    }


def _approach_stats(traj, goal_rect):
    valid = [p for p in traj["points"] if p["source"] != "missing"]
    if not valid:
        return {
            "dist_start": None,
            "dist_end": None,
            "dist_min": None,
            "approaches": False,
            "toward": False,
            "entered": False,
            "entered_from_outside": False,
            "started_inside": False,
            "inside_run": 0,
            "intersect": False,
        }
    dists = [_point_rect_distance(p["x"], p["y"], goal_rect) for p in valid]
    dist_start = dists[0]
    dist_end = dists[-1]
    dist_min = min(dists)
    started_inside = _point_in_rect(valid[0]["x"], valid[0]["y"], goal_rect)
    approaches = (dist_start - dist_min) >= SHOT_MIN_GOAL_APPROACH_PX
    gx, gy = _rect_center(goal_rect)
    toward = (traj["dx"] * (gx - traj["start_x"]) + traj["dy"] * (gy - traj["start_y"])) > 0
    inside_run = 0
    best_run = 0
    entered = False
    for p in valid:
        # Goal entry evidence uses observed window points, not the possession-end seed.
        if p.get("frame") is None:
            continue
        if _point_in_rect(p["x"], p["y"], goal_rect):
            entered = True
            inside_run += 1
            best_run = max(best_run, inside_run)
        else:
            inside_run = 0
    entered_from_outside = (not started_inside) and entered
    if entered_from_outside:
        toward = True
        approaches = True
    intersect = False
    if traj["start_x"] is not None:
        intersect = _segment_intersects_rect(
            traj["start_x"], traj["start_y"], traj["end_x"], traj["end_y"], goal_rect
        )
    return {
        "dist_start": dist_start,
        "dist_end": dist_end,
        "dist_min": dist_min,
        "approaches": approaches,
        "toward": toward,
        "entered": entered,
        "entered_from_outside": entered_from_outside,
        "started_inside": started_inside,
        "inside_run": best_run,
        "intersect": intersect,
    }


def _confidence_label(traj, approach, movement_ok):
    coverage = traj["coverage"]
    detected_ratio = (traj["detected"] / traj["n"]) if traj["n"] else 0.0
    movement = traj["movement_px"]
    if not movement_ok or not approach["toward"] or not approach["approaches"]:
        return "LOW"
    if traj["missing_ratio"] > SHOT_MAX_MISSING_BALL_RATIO:
        return "LOW"
    if coverage < 0.40:
        return "LOW"
    high = (
        movement >= SHOT_MIN_BALL_MOVEMENT_PX * 1.5
        and coverage >= 0.55
        and detected_ratio >= 0.20
        and approach["approaches"]
        and approach["toward"]
    )
    if high:
        return "HIGH"
    return "MEDIUM"


def classify_shot_interval(interval, nxt, teams, frame_df, last_frame):
    shooter = interval["stable_id"]
    team = teams.get(shooter)
    end_frame = interval["end_frame"]
    reasons = []

    if shooter is None:
        return _reject("invalid_shooter", interval, nxt, team, None, None, None, reasons)

    if team not in VALID_TEAMS:
        return _reject(
            "unknown_or_invalid_team",
            interval,
            nxt,
            team,
            None,
            None,
            None,
            reasons,
        )

    if interval["frames"] < SHOT_MIN_POSSESSION_FRAMES:
        return _reject(
            "possession_too_short",
            interval,
            nxt,
            team,
            _target_goal_for_team(team),
            None,
            None,
            reasons,
        )

    target = _target_goal_for_team(team)
    if target is None:
        return _reject("no_target_goal", interval, nxt, team, None, None, None, reasons)

    zones = _goal_zones()
    goal_rect = zones[target]

    if nxt is not None:
        next_team = teams.get(nxt["stable_id"])
        gap = max(0, nxt["start_frame"] - end_frame - 1)
        if (
            next_team == team
            and nxt["stable_id"] != shooter
            and gap <= PASS_MAX_TRANSITION_FRAMES
        ):
            return _reject(
                "same_team_pass_not_shot",
                interval,
                nxt,
                team,
                target,
                None,
                None,
                reasons,
            )
        window_end = min(
            end_frame + SHOT_GOAL_APPROACH_WINDOW_FRAMES,
            nxt["start_frame"] - 1,
            last_frame,
        )
    else:
        window_end = min(end_frame + SHOT_GOAL_APPROACH_WINDOW_FRAMES, last_frame)

    if window_end <= end_frame:
        return _reject(
            "no_ball_window_after_possession",
            interval,
            nxt,
            team,
            target,
            None,
            None,
            reasons,
        )

    start_row = frame_df[frame_df["frame"] == end_frame]
    start_xy = None
    if len(start_row):
        start_xy = _ball_xy(start_row.iloc[0])
        if start_xy is not None:
            start_xy = (start_xy[0], start_xy[1], start_xy[2])

    window = _window_rows(frame_df, end_frame, window_end)
    early_end = min(end_frame + SHOT_MAX_TRANSITION_FRAMES, window_end)
    early_window = _window_rows(frame_df, end_frame, early_end)
    traj = _trajectory(early_window if len(early_window) else window, start_xy)
    # Approach uses the longer goal-approach window
    full_traj = _trajectory(window, start_xy)
    if full_traj["n"] > traj["n"]:
        # keep early movement, but merge later points for approach/goal
        approach_traj = full_traj
        approach_traj["movement_px"] = max(traj["movement_px"], full_traj["movement_px"])
        approach_traj["dx"] = full_traj["dx"]
        approach_traj["dy"] = full_traj["dy"]
        approach_traj["start_x"] = traj["start_x"] if traj["start_x"] is not None else full_traj["start_x"]
        approach_traj["start_y"] = traj["start_y"] if traj["start_y"] is not None else full_traj["start_y"]
        approach_traj["end_x"] = full_traj["end_x"]
        approach_traj["end_y"] = full_traj["end_y"]
    else:
        approach_traj = traj

    if approach_traj["start_x"] is None or approach_traj["end_x"] is None:
        return _reject(
            "insufficient_ball_positions",
            interval,
            nxt,
            team,
            target,
            approach_traj,
            None,
            reasons,
        )

    if approach_traj["n"] > 0 and approach_traj["missing_ratio"] > 0.80:
        return _reject(
            "too_many_missing_ball_frames",
            interval,
            nxt,
            team,
            target,
            approach_traj,
            None,
            reasons,
        )

    movement_ok = approach_traj["movement_px"] >= SHOT_MIN_BALL_MOVEMENT_PX
    if not movement_ok:
        return _reject(
            "ball_movement_too_small",
            interval,
            nxt,
            team,
            target,
            approach_traj,
            None,
            reasons,
        )

    approach = _approach_stats(approach_traj, goal_rect)
    if approach.get("started_inside"):
        return _reject(
            "ball_already_in_target_goal",
            interval,
            nxt,
            team,
            target,
            approach_traj,
            approach,
            reasons,
        )
    if not approach["toward"]:
        return _reject(
            "not_toward_opponent_goal",
            interval,
            nxt,
            team,
            target,
            approach_traj,
            approach,
            reasons,
        )
    if not approach["approaches"]:
        return _reject(
            "does_not_approach_goal",
            interval,
            nxt,
            team,
            target,
            approach_traj,
            approach,
            reasons,
        )

    confidence = _confidence_label(approach_traj, approach, movement_ok)
    if confidence == "LOW":
        return _reject(
            "low_confidence",
            interval,
            nxt,
            team,
            target,
            approach_traj,
            approach,
            reasons,
            confidence="LOW",
        )

    on_target = _on_target(approach, approach_traj, goal_rect)
    is_goal = False
    goal_reason = ""
    if on_target is True:
        if (
            approach.get("entered_from_outside")
            and approach["inside_run"] >= SHOT_GOAL_INSIDE_FRAMES
        ):
            is_goal = True
            goal_reason = "ball_inside_goal_zone"
        else:
            goal_reason = "on_target_but_no_goal_entry"
    else:
        goal_reason = "not_on_target"

    transition_frames = max(0, (window_end - end_frame))
    return {
        "accepted": True,
        "candidate_type": "shot",
        "reason": goal_reason,
        "confidence": confidence,
        "on_target": on_target,
        "goal": is_goal,
        "shooter": shooter,
        "team": team,
        "target_goal": target,
        "interval": interval,
        "traj": approach_traj,
        "approach": approach,
        "transition_frames": transition_frames,
        "window_end": window_end,
    }


def _on_target(approach, traj, goal_rect):
    if approach.get("entered_from_outside"):
        return True
    if approach["intersect"] and approach.get("toward"):
        return True
    if (
        approach["dist_min"] is not None
        and approach["dist_min"] <= SHOT_ON_TARGET_MAX_DIST_PX
        and approach.get("toward")
        and approach.get("approaches")
    ):
        return True
    return False


def _reject(reason, interval, nxt, team, target, traj, approach, reasons, confidence="LOW"):
    dist = None
    movement = None
    coverage = None
    if traj:
        movement = traj.get("movement_px")
        coverage = traj.get("coverage")
    if approach and approach.get("dist_min") is not None:
        dist = approach["dist_min"]
    return {
        "accepted": False,
        "candidate_type": "shot_candidate",
        "reason": reason,
        "confidence": confidence,
        "on_target": False,
        "goal": False,
        "shooter": interval["stable_id"],
        "team": team,
        "target_goal": target,
        "interval": interval,
        "traj": traj,
        "approach": approach,
        "transition_frames": max(
            0,
            (nxt["start_frame"] - interval["end_frame"] - 1) if nxt is not None else 0,
        ),
        "goal_distance": dist,
        "movement_px": movement,
        "coverage": coverage,
    }


def detect_shots(frame_state_csv, teams_csv, fps):
    frame_df = pd.read_csv(frame_state_csv)
    teams = _load_teams(teams_csv)
    intervals = _confirmed_intervals(frame_df)
    last_frame = int(frame_df["frame"].max()) if len(frame_df) else 0

    validation = []
    shots = []
    event_id = 1
    counts = {
        "confirmed_intervals": len(intervals),
        "shot_candidates": 0,
        "confirmed_shots": 0,
        "shots_on_target": 0,
        "goals": 0,
        "rejected": 0,
        "rejected_reasons": {},
    }

    seen_keys = set()

    for i, interval in enumerate(intervals):
        nxt = intervals[i + 1] if i + 1 < len(intervals) else None
        counts["shot_candidates"] += 1
        result = classify_shot_interval(interval, nxt, teams, frame_df, last_frame)
        traj = result.get("traj") or {}
        approach = result.get("approach") or {}
        key = (interval["end_frame"], interval["stable_id"])
        duplicate = key in seen_keys
        seen_keys.add(key)

        on_target_out = result["on_target"]
        if on_target_out is True:
            on_target_csv = True
        elif result["accepted"]:
            on_target_csv = False
        else:
            on_target_csv = False

        if duplicate:
            result["accepted"] = False
            result["reason"] = "duplicate_shot_event"
            result["goal"] = False
            on_target_csv = False

        val = {
            "frame": interval["end_frame"],
            "shooter": interval["stable_id"],
            "team": result.get("team") or "",
            "candidate_type": result["candidate_type"],
            "accepted": result["accepted"],
            "on_target": on_target_csv if result["accepted"] else False,
            "goal": bool(result["goal"]) if result["accepted"] else False,
            "confidence": result["confidence"],
            "reason": result["reason"],
            "ball_coverage": round(traj.get("coverage") or 0.0, 3) if traj else "",
            "movement_px": round(traj.get("movement_px") or 0.0, 1) if traj else "",
            "target_goal": result.get("target_goal") or "",
            "goal_distance": (
                round(approach["dist_min"], 1)
                if approach and approach.get("dist_min") is not None
                else ""
            ),
        }
        validation.append(val)

        if not result["accepted"]:
            counts["rejected"] += 1
            counts["rejected_reasons"][result["reason"]] = (
                counts["rejected_reasons"].get(result["reason"], 0) + 1
            )
            continue

        # Sanity: no goal without shot; no goal without on-target
        is_goal = bool(result["goal"]) and on_target_csv is True
        shot_row = {
            "event_id": event_id,
            "frame": interval["end_frame"],
            "time_s": round(interval["end_time_s"], 4) if interval["end_time_s"] is not None else "",
            "shooter_stable_id": interval["stable_id"],
            "team_id": result["team"],
            "target_goal": result["target_goal"],
            "ball_start_x": round(traj["start_x"], 1) if traj.get("start_x") is not None else "",
            "ball_start_y": round(traj["start_y"], 1) if traj.get("start_y") is not None else "",
            "ball_end_x": round(traj["end_x"], 1) if traj.get("end_x") is not None else "",
            "ball_end_y": round(traj["end_y"], 1) if traj.get("end_y") is not None else "",
            "ball_movement_px": round(traj.get("movement_px") or 0.0, 1),
            "transition_frames": result.get("transition_frames") or 0,
            "confidence": result["confidence"],
            "on_target": on_target_csv,
            "goal": is_goal,
        }
        shots.append(shot_row)
        counts["confirmed_shots"] += 1
        if on_target_csv:
            counts["shots_on_target"] += 1
        if is_goal:
            counts["goals"] += 1
        event_id += 1

    return intervals, shots, validation, counts, fps


def _write_shooting_stats(shots, teams, suffix):
    tag = f"_{suffix}" if suffix else ""
    team_totals = {tid: {"shots": 0, "shots_on_target": 0, "goals": 0} for tid in ("team_a", "team_b")}
    player_totals = {}
    for shot in shots:
        team = shot["team_id"]
        sid = shot["shooter_stable_id"]
        if team in team_totals:
            team_totals[team]["shots"] += 1
            if shot["on_target"] is True:
                team_totals[team]["shots_on_target"] += 1
            if shot["goal"] is True:
                team_totals[team]["goals"] += 1
        if sid not in player_totals:
            player_totals[sid] = {
                "stable_id": sid,
                "team_id": team,
                "shots": 0,
                "shots_on_target": 0,
                "goals": 0,
            }
        player_totals[sid]["shots"] += 1
        if shot["on_target"] is True:
            player_totals[sid]["shots_on_target"] += 1
        if shot["goal"] is True:
            player_totals[sid]["goals"] += 1

    team_rows = [
        {"team_id": tid, **team_totals[tid]} for tid in ("team_a", "team_b")
    ]
    player_rows = [player_totals[sid] for sid in sorted(player_totals)]
    team_path = _write_csv(
        ANALYTICS_DIR / f"team_shooting_stats{tag}.csv",
        team_rows,
        ["team_id", "shots", "shots_on_target", "goals"],
    )
    player_path = _write_csv(
        ANALYTICS_DIR / f"player_shooting_stats{tag}.csv",
        player_rows,
        ["stable_id", "team_id", "shots", "shots_on_target", "goals"],
    )
    return team_path, player_path


def write_shot_validation_video(
    video_path,
    frame_state_csv,
    shots,
    validation,
    output_path,
):
    frame_df = pd.read_csv(frame_state_csv)
    state_by_frame = {int(r["frame"]): r for _, r in frame_df.iterrows()}
    shot_by_frame = {int(s["frame"]): s for s in shots}
    cand_by_frame = {}
    for row in validation:
        cand_by_frame.setdefault(int(row["frame"]), []).append(row)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    min_frame = int(frame_df["frame"].min())
    max_frame = int(frame_df["frame"].max())
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

    zones = _goal_zones()
    active_label = None
    active_until = -1

    frame_index = min_frame
    while frame_index <= max_frame:
        ret, image = cap.read()
        if not ret:
            break

        lx1, ly1, lx2, ly2 = zones["left"]
        rx1, ry1, rx2, ry2 = zones["right"]
        cv2.rectangle(image, (lx1, ly1), (lx2, ly2), (0, 200, 255), 2)
        cv2.putText(
            image, "goal L", (lx1, max(20, ly1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2, cv2.LINE_AA,
        )
        cv2.rectangle(image, (rx1, ry1), (rx2, ry2), (255, 200, 0), 2)
        cv2.putText(
            image, "goal R", (rx1, max(20, ry1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 200, 0), 2, cv2.LINE_AA,
        )

        state = state_by_frame.get(frame_index)
        if state is not None and pd.notna(state.get("ball_x")) and pd.notna(state.get("ball_y")):
            source = str(state.get("ball_source", "")).strip().lower()
            if source != "missing":
                bx, by = int(state["ball_x"]), int(state["ball_y"])
                color = (0, 255, 255) if source == "detected" else (255, 255, 0)
                cv2.circle(image, (bx, by), 8, color, -1)

        if frame_index in shot_by_frame:
            s = shot_by_frame[frame_index]
            label = "SHOT"
            if s["on_target"] is True:
                label = "ON TARGET"
            if s["goal"] is True:
                label = "GOAL"
            active_label = (
                f"{label} id={s['shooter_stable_id']} {s['team_id']} -> {s['target_goal']} {s['confidence']}"
            )
            active_until = frame_index + int(fps * 2)
        elif frame_index in cand_by_frame and frame_index not in shot_by_frame:
            c = cand_by_frame[frame_index][0]
            if not c["accepted"]:
                active_label = f"CAND reject {c['reason']} sid={c['shooter']}"
                active_until = frame_index + int(fps * 1.2)

        if active_label and frame_index <= active_until:
            cv2.putText(
                image, active_label, (30, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2, cv2.LINE_AA,
            )

        writer.write(image)
        frame_index += 1

    cap.release()
    writer.release()
    return output_path


def run_shot_detection(frame_state_csv, teams_csv, video_path, suffix=""):
    EVENTS_OUTPUT.mkdir(parents=True, exist_ok=True)
    ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)
    fps = _video_fps(video_path)
    tag = f"_{suffix}" if suffix else ""

    _, shots, validation, counts, fps = detect_shots(
        frame_state_csv, teams_csv, fps
    )
    teams = _load_teams(teams_csv)

    shots_path = EVENTS_OUTPUT / f"shots{tag}.csv"
    val_path = EVENTS_OUTPUT / f"shot_validation{tag}.csv"
    _write_csv(
        shots_path,
        shots,
        [
            "event_id",
            "frame",
            "time_s",
            "shooter_stable_id",
            "team_id",
            "target_goal",
            "ball_start_x",
            "ball_start_y",
            "ball_end_x",
            "ball_end_y",
            "ball_movement_px",
            "transition_frames",
            "confidence",
            "on_target",
            "goal",
        ],
    )
    _write_csv(
        val_path,
        validation,
        [
            "frame",
            "shooter",
            "team",
            "candidate_type",
            "accepted",
            "on_target",
            "goal",
            "confidence",
            "reason",
            "ball_coverage",
            "movement_px",
            "target_goal",
            "goal_distance",
        ],
    )
    team_path, player_path = _write_shooting_stats(shots, teams, suffix)

    video_out = None
    if SHOT_WRITE_VALIDATION_VIDEO:
        video_out = EVENTS_OUTPUT / f"shot_validation{tag}.mp4"
        write_shot_validation_video(
            video_path, frame_state_csv, shots, validation, video_out
        )

    by_team = {"team_a": 0, "team_b": 0}
    for s in shots:
        if s["team_id"] in by_team:
            by_team[s["team_id"]] += 1

    print("Shot detection (MVP, camera-pixel, stable_id-level):")
    print(f"  FPS                            : {fps:.4f}")
    print(f"  SHOT_MAX_TRANSITION_FRAMES     : {SHOT_MAX_TRANSITION_FRAMES}")
    print(f"  SHOT_MIN_BALL_MOVEMENT_PX      : {SHOT_MIN_BALL_MOVEMENT_PX}")
    print(f"  SHOT_GOAL_APPROACH_WINDOW      : {SHOT_GOAL_APPROACH_WINDOW_FRAMES}")
    print(f"  GOAL_ZONE_LEFT                 : {GOAL_ZONE_LEFT}")
    print(f"  GOAL_ZONE_RIGHT                : {GOAL_ZONE_RIGHT}")
    print(f"  TEAM_DEFENDS_GOAL              : {TEAM_DEFENDS_GOAL}")
    print(f"  confirmed intervals            : {counts['confirmed_intervals']}")
    print(f"  shot candidates                : {counts['shot_candidates']}")
    print(f"  confirmed shots                : {counts['confirmed_shots']}")
    print(f"  shots by team                  : {by_team}")
    print(f"  shots on target                : {counts['shots_on_target']}")
    print(f"  goals                          : {counts['goals']}")
    print(f"  rejected candidates            : {counts['rejected']}")
    print(f"  rejection reasons              : {counts['rejected_reasons']}")
    print(f"  shots CSV                      : {shots_path}")
    print(f"  validation CSV                 : {val_path}")
    if video_out:
        print(f"  validation video               : {video_out}")

    return {
        "counts": counts,
        "shots": shots,
        "validation": validation,
        "shots_csv": shots_path,
        "validation_csv": val_path,
        "team_stats_csv": team_path,
        "player_stats_csv": player_path,
        "validation_video": video_out,
        "fps": fps,
        "by_team": by_team,
        "goal_zones": _goal_zones(),
    }
