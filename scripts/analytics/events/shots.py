"""
Shots, shots on target and goals, measured against the goals seen in the video.

Where the goals are comes from scripts/vision/goals.py (detected posts + net,
tracked through camera pans). A player's possession ends; the ball's flight
over the next SHOT_WINDOW_S is followed relative to the goal box of the same
frame, so a camera pan does not look like ball movement:

  goal      the ball goes deep into the goal box and stays there
            (GOAL_MIN_INSIDE_S) or disappears in it (GOAL_VANISH_S), with no
            player on it: a ball at a keeper's feet on the line, or in a
            goalmouth scramble, projects into the box too, but a ball in the
            net has nobody on it (GOAL_FREE_BALL_MARGIN).
  shot      the ball leaves the shooter's feet, is struck (SHOT_MIN_SPEED_BH_S;
            faster than SHOT_MAX_SPEED_BH_S is a ball-tracking jump, not a
            kick) from within SHOT_MAX_START_GH, travels toward the goal
            (within SHOT_MAX_AIM_ANGLE_DEG, aim within SHOT_AIM_MARGIN of the
            box) and gets closer to it, and either gets near it
            (SHOT_NEAR_GOAL_GH) or is stopped by the other team (block / save).
  on target a goal, or a shot aimed inside the box that reached it or was
            saved near it.
A ball played to a teammate is a pass, not a shot. A shot only counts if a
goal is in view; shots at an off-screen goal are not measured.

Distances are in goal box heights (GH, ~2 m) and speeds in the shooter's
body heights per second (BH/s, ~1.8 m/s), so zoom cancels out.
"""

from __future__ import annotations

import csv
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from config.config import (
    EVENTS_OUTPUT,
    GOAL_FREE_BALL_MARGIN,
    GOAL_INSIDE_INSET,
    OUTPUT_DIR,
    SHOT_AIM_MARGIN,
    SHOT_MAX_AIM_ANGLE_DEG,
    SHOT_MAX_BALL_TO_SHOOTER_BH,
    SHOT_MAX_SPEED_BH_S,
    SHOT_MAX_START_GH,
    SHOT_MIN_APPROACH_GH,
    SHOT_MIN_SPEED_BH_S,
    SHOT_NEAR_GOAL_GH,
    WRITE_DEBUG_VIDEOS,
)

from scripts.analytics.events.timing import EventTiming
from scripts.analytics.events.passes import (
    VALID_TEAMS,
    _confirmed_intervals,
    _load_teams,
    _video_fps,
)
from scripts.vision.goals import load_goals

ANALYTICS_DIR = OUTPUT_DIR / "analytics"

SHOT_FIELDS = [
    "event_id", "frame", "time_s", "shooter_stable_id", "team_id", "target_goal",
    "ball_start_x", "ball_start_y", "start_distance_gh", "speed_bh_s", "min_distance_gh",
    "confidence", "on_target", "goal", "outcome",
]
VALIDATION_FIELDS = [
    "frame", "time_s", "shooter", "team", "accepted", "on_target", "goal", "outcome", "reason",
    "start_distance_gh", "speed_bh_s", "aim_offset", "min_distance_gh", "inside_frames", "goal_in_view",
]


def _write_csv(path, rows, fieldnames):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _rect_distance(x, y, box):
    x1, y1, x2, y2 = box
    dx = max(x1 - x, 0.0, x - x2)
    dy = max(y1 - y, 0.0, y - y2)
    return float(np.hypot(dx, dy))


def _inside(x, y, box, inset=0.0):
    x1, y1, x2, y2 = box
    ix, iy = inset * (x2 - x1), inset * (y2 - y1)
    return x1 + ix <= x <= x2 - ix and y1 + iy <= y <= y2 - iy


def _ray_hits_box(p, v, half_w, half_h):
    """Ray p + t v (t > 0) against the box [-half_w, half_w] x [-half_h, half_h]."""
    t_lo, t_hi = 0.0, np.inf
    for pi, vi, h in ((p[0], v[0], half_w), (p[1], v[1], half_h)):
        if abs(vi) < 1e-9:
            if abs(pi) > h:
                return False
            continue
        a, b = (-h - pi) / vi, (h - pi) / vi
        t_lo, t_hi = max(t_lo, min(a, b)), min(t_hi, max(a, b))
    return t_lo <= t_hi


def _aim_offset(p, v, w, h):
    """How far the aim misses the goal box, in box widths (0 = inside)."""
    for margin in np.arange(0.0, 3.01, 0.05):
        if _ray_hits_box(p, v, w * (0.5 + margin), h * 0.5 + margin * w):
            return round(float(margin), 2)
    return None


class _Scene:
    """Per-frame lookups: ball, goals, people."""

    def __init__(self, frame_df, goals, people):
        fd = frame_df.sort_values("frame")
        self.ball = {}
        for r in fd.itertuples(index=False):
            src = str(r.ball_source).strip().lower()
            if src != "missing" and pd.notna(r.ball_x) and pd.notna(r.ball_y):
                self.ball[int(r.frame)] = (float(r.ball_x), float(r.ball_y))
        self.time = dict(zip(fd["frame"].astype(int), fd["time_s"]))
        self.goals = goals
        self.people = people

    def goal_near(self, frame, ref):
        """The goal box in `frame` that continues `ref` (same physical goal)."""
        boxes = self.goals.get(frame)
        if not boxes:
            return None
        if ref is None:
            return None
        rc = ((ref[0] + ref[2]) / 2, (ref[1] + ref[3]) / 2)
        best = min(boxes, key=lambda b: np.hypot((b[0] + b[2]) / 2 - rc[0], (b[1] + b[3]) / 2 - rc[1]))
        # a goal cannot jump more than half its own size between nearby frames
        if np.hypot((best[0] + best[2]) / 2 - rc[0], (best[1] + best[3]) / 2 - rc[1]) > 0.5 * max(
            ref[2] - ref[0], ref[3] - ref[1]
        ):
            return None
        return best

    def free(self, frame, x, y):
        """Nobody on the ball: it is not on or right beside a player (their
        box widened by GOAL_FREE_BALL_MARGIN of its width each side and
        extended a little below the feet)."""
        for x1, y1, x2, y2 in self.people.get(frame, ()):
            mx = GOAL_FREE_BALL_MARGIN * (x2 - x1)
            if x1 - mx <= x <= x2 + mx and y1 <= y <= y2 + 0.1 * (y2 - y1):
                return False
        return True


def _load_people(coordinate_csv):
    """people: {frame: [box]}; feet: {(frame, stable_id): (x, y, body height)}."""
    people, feet = {}, {}
    if coordinate_csv is None or not Path(coordinate_csv).exists():
        return people, feet
    df = pd.read_csv(coordinate_csv)
    df = df[df["class"] == "person"]
    for r in df.itertuples(index=False):
        f = int(r.frame)
        people.setdefault(f, []).append((r.x1, r.y1, r.x2, r.y2))
        if pd.notna(r.stable_id):
            feet[(f, int(r.stable_id))] = ((r.x1 + r.x2) / 2.0, float(r.y2), float(r.y2 - r.y1))
    return people, feet


def _shooter_feet(feet, sid, frame, timing):
    for d in range(0, timing.shot_window):
        for f in (frame - d, frame + d):
            hit = feet.get((f, sid))
            if hit:
                return hit
    return None


def _flight(scene, start, end, timing):
    """Ball positions after the touch, relative to the goal it heads to."""
    first_ball = None
    for f in range(start, end + 1):
        if f in scene.ball:
            first_ball = (f, scene.ball[f])
            break
    if first_ball is None:
        return None
    f0, (bx, by) = first_ball
    # target: the goal in view closest to the ball at the start of the flight
    target = None
    for f in range(f0, min(end, f0 + timing.shot_aim) + 1):
        boxes = scene.goals.get(f)
        if boxes and f in scene.ball:
            x, y = scene.ball[f]
            target = (f, min(boxes, key=lambda b: _rect_distance(x, y, b) / max(b[3] - b[1], 1.0)))
            break
    if target is None:
        return {"goal_in_view": False}

    pts = []
    ref = target[1]
    for f in range(target[0], end + 1):
        box = scene.goal_near(f, ref)
        if box is None:
            continue
        ref = box
        gh = max(box[3] - box[1], 1.0)
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        if f in scene.ball:
            x, y = scene.ball[f]
            pts.append({
                "frame": f, "x": x, "y": y, "box": box,
                "rel": ((x - cx) / gh, (y - cy) / gh),
                "dist": _rect_distance(x, y, box) / gh,
                "inside": _inside(x, y, box, GOAL_INSIDE_INSET) and scene.free(f, x, y),
            })
        else:
            pts.append({"frame": f, "box": box, "missing": True})
    return {"goal_in_view": True, "target": target[1], "points": pts}


def _goal_scored(points, timing):
    """Ball stays in the net, or disappears in it."""
    seen = [p for p in points if not p.get("missing")]
    inside = sum(1 for p in seen if p["inside"])
    if inside >= timing.goal_min_inside:
        return True, inside
    # last sighting inside the net, then gone
    last_inside = None
    for i, p in enumerate(points):
        if not p.get("missing"):
            last_inside = i if p["inside"] else None
    if last_inside is not None:
        gone = len(points) - 1 - last_inside
        if gone >= timing.goal_vanish:
            return True, inside
    return False, inside


def classify_shot(interval, nxt, teams, scene, feet, last_frame, timing):
    shooter = interval["stable_id"]
    team = teams.get(shooter)
    end = interval["end_frame"]
    out = {
        "frame": end, "time_s": interval.get("end_time_s"), "shooter": shooter, "team": team or "",
        "accepted": False, "on_target": False, "goal": False, "outcome": "",
    }

    def reject(reason, **extra):
        out.update(extra, reason=reason)
        return out

    if team not in VALID_TEAMS:
        return reject("unknown_or_invalid_team")
    if interval["frames"] < timing.shot_min_possession:
        return reject("possession_too_short")

    shooter_feet = _shooter_feet(feet, shooter, end, timing)
    ball_at_touch = scene.ball.get(end)
    if shooter_feet and ball_at_touch:
        gap_bh = np.hypot(ball_at_touch[0] - shooter_feet[0], ball_at_touch[1] - shooter_feet[1]) / shooter_feet[2]
        if gap_bh > SHOT_MAX_BALL_TO_SHOOTER_BH:
            return reject("ball_not_at_shooter")

    flight_end = min(end + timing.shot_window, last_frame)
    # the net check runs a little longer: a ball in the net can vanish
    net_end = min(flight_end + timing.goal_vanish, last_frame)
    flight = _flight(scene, end, net_end, timing)
    if flight is None:
        return reject("no_ball_after_touch")
    if not flight["goal_in_view"]:
        return reject("no_goal_in_view", goal_in_view=False)
    out["goal_in_view"] = True
    pts = [p for p in flight["points"] if not p.get("missing")]
    if len(pts) < 3:
        return reject("too_few_ball_positions")

    # stop the flight where someone else takes the ball (unless it is in the net)
    next_start = nxt["start_frame"] if nxt is not None else None
    in_flight = [p for p in pts if p["frame"] <= flight_end and (next_start is None or p["frame"] < next_start)]
    if len(in_flight) < 2:
        in_flight = pts[:2]

    # drop single-frame jumps (the ball track briefly on another object);
    # if many points jump, the whole flight is unreliable
    bh = shooter_feet[2] if shooter_feet else None
    if bh:
        kept = [in_flight[0]]
        for b in in_flight[1:]:
            a = kept[-1]
            step = np.hypot(b["rel"][0] - a["rel"][0], b["rel"][1] - a["rel"][1]) * (a["box"][3] - a["box"][1])
            if step / ((b["frame"] - a["frame"]) / timing.fps) / bh <= SHOT_MAX_SPEED_BH_S:
                kept.append(b)
        track_jumps = len(in_flight) - len(kept)
        in_flight = kept if len(kept) >= 2 else in_flight
    else:
        track_jumps = 0

    start = in_flight[0]
    out["start_distance_gh"] = round(start["dist"], 2)
    if start["inside"] or start["dist"] <= 0.0:
        return reject("started_in_goal")
    if start["dist"] > SHOT_MAX_START_GH:
        return reject("too_far_from_goal")

    aim = [p for p in in_flight if p["frame"] <= start["frame"] + timing.shot_aim]
    if len(aim) < 2:
        aim = in_flight[:2]
    p0, p1 = np.array(aim[0]["rel"]), np.array(aim[-1]["rel"])
    dt = (aim[-1]["frame"] - aim[0]["frame"]) / timing.fps
    gh = aim[0]["box"][3] - aim[0]["box"][1]
    speed = float(np.linalg.norm(p1 - p0)) * gh / dt / bh if (bh and dt > 0) else 0.0
    out["speed_bh_s"] = round(speed, 2)
    unreliable = track_jumps > 0.25 * (len(in_flight) + track_jumps) or speed > SHOT_MAX_SPEED_BH_S

    box = start["box"]
    w_gh = (box[2] - box[0]) / max(box[3] - box[1], 1.0)
    offset = _aim_offset(p0, p1 - p0, w_gh, 1.0)
    out["aim_offset"] = "" if offset is None else offset
    # direction of travel vs direction to the goal centre (the box test alone
    # passes anything that starts close to the goal)
    v, to_goal = p1 - p0, -p0
    norm = float(np.linalg.norm(v) * np.linalg.norm(to_goal))
    angle = float(np.degrees(np.arccos(np.clip(v @ to_goal / norm, -1.0, 1.0)))) if norm > 0 else 180.0
    min_dist = min(p["dist"] for p in in_flight)
    out["min_distance_gh"] = round(min_dist, 2)

    scored, inside = _goal_scored(flight["points"], timing)
    out["inside_frames"] = inside
    # a goal still needs a real strike toward the goal on a clean ball track
    if scored and (angle >= 90.0 or unreliable):
        scored = False

    next_team = teams.get(nxt["stable_id"]) if nxt is not None else None
    gap = (nxt["start_frame"] - end - 1) if nxt is not None else None
    # a teammate who collects a rebound after the ball reached the goal did
    # not receive a pass
    reached = next((p["frame"] for p in pts if p["dist"] <= 0.5), None)
    to_teammate = (
        next_team == team and nxt["stable_id"] != shooter and gap is not None and gap <= timing.pass_max_transition
        and (reached is None or nxt["start_frame"] < reached)
    )

    if not scored:
        if to_teammate:
            return reject("pass_to_teammate")
        if speed < SHOT_MIN_SPEED_BH_S:
            return reject("not_struck")
        if unreliable:
            return reject("ball_track_jump")
        # straight at the box and moving toward it, or roughly toward the
        # goal centre and within the wide-shot margin
        at_box = offset == 0.0 and angle < 90.0
        if not at_box and (angle > SHOT_MAX_AIM_ANGLE_DEG or offset is None or offset > SHOT_AIM_MARGIN):
            return reject("not_aimed_at_goal")
        if min_dist > start["dist"] - SHOT_MIN_APPROACH_GH:
            return reject("does_not_approach_goal")
    stopped_by_opponent = (
        next_team in VALID_TEAMS and next_team != team and gap is not None and gap <= timing.shot_window
    )
    near = min_dist <= SHOT_NEAR_GOAL_GH
    if not (scored or near or stopped_by_opponent):
        return reject("did_not_reach_goal")

    saved_near_goal = stopped_by_opponent and near
    on_target = scored or (offset == 0.0 and (min_dist <= 0.3 or saved_near_goal))
    if scored:
        outcome = "goal"
    elif on_target:
        outcome = "saved" if stopped_by_opponent else "on_target"
    elif stopped_by_opponent and not near:
        outcome = "blocked"
    else:
        outcome = "off_target"

    confidence = "HIGH" if (scored or (offset == 0.0 and speed >= 1.5 * SHOT_MIN_SPEED_BH_S)) else "MEDIUM"
    out.update(
        accepted=True, on_target=bool(on_target), goal=bool(scored), outcome=outcome, reason=outcome,
        confidence=confidence, target=flight["target"], ball_start=(start["x"], start["y"]),
    )
    return out


def detect_shots(frame_state_csv, teams_csv, fps, goals_csv, coordinate_csv=None):
    timing = EventTiming(fps)
    frame_df = pd.read_csv(frame_state_csv)
    teams = _load_teams(teams_csv)
    intervals = _confirmed_intervals(frame_df, timing.possession_merge_gap)
    last_frame = int(frame_df["frame"].max()) if len(frame_df) else 0
    goals = load_goals(goals_csv) or {}
    people, feet = _load_people(coordinate_csv)
    scene = _Scene(frame_df, goals, people)

    shots, validation = [], []
    counts = {"confirmed_intervals": len(intervals), "confirmed_shots": 0, "shots_on_target": 0,
              "goals": 0, "rejected_reasons": {}}
    busy_until = -1
    for i, interval in enumerate(intervals):
        nxt = intervals[i + 1] if i + 1 < len(intervals) else None
        r = classify_shot(interval, nxt, teams, scene, feet, last_frame, timing)
        if r["accepted"] and interval["end_frame"] <= busy_until:
            # possession flicker around one strike: the first touch is the shot
            r.update(accepted=False, on_target=False, goal=False, outcome="", reason="duplicate_of_previous_shot")
        validation.append(r)
        if not r["accepted"]:
            counts["rejected_reasons"][r["reason"]] = counts["rejected_reasons"].get(r["reason"], 0) + 1
            continue
        busy_until = interval["end_frame"] + timing.shot_window
        tx1, ty1, tx2, ty2 = r["target"]
        shots.append({
            "event_id": len(shots) + 1,
            "frame": interval["end_frame"],
            "time_s": round(interval["end_time_s"], 4) if interval["end_time_s"] is not None else "",
            "shooter_stable_id": interval["stable_id"],
            "team_id": r["team"],
            "target_goal": f"{tx1:.0f},{ty1:.0f},{tx2:.0f},{ty2:.0f}",
            "ball_start_x": round(r["ball_start"][0], 1),
            "ball_start_y": round(r["ball_start"][1], 1),
            "start_distance_gh": r.get("start_distance_gh", ""),
            "speed_bh_s": r.get("speed_bh_s", ""),
            "min_distance_gh": r.get("min_distance_gh", ""),
            "confidence": r["confidence"],
            "on_target": r["on_target"],
            "goal": r["goal"],
            "outcome": r["outcome"],
        })
        counts["confirmed_shots"] += 1
        counts["shots_on_target"] += int(r["on_target"])
        counts["goals"] += int(r["goal"])
    return shots, validation, counts


def _write_shooting_stats(shots, suffix):
    tag = f"_{suffix}" if suffix else ""
    team_totals = {tid: {"shots": 0, "shots_on_target": 0, "goals": 0} for tid in ("team_a", "team_b")}
    player_totals = {}
    for shot in shots:
        team, sid = shot["team_id"], shot["shooter_stable_id"]
        p = player_totals.setdefault(sid, {"stable_id": sid, "team_id": team, "shots": 0, "shots_on_target": 0, "goals": 0})
        for totals in ([team_totals[team]] if team in team_totals else []) + [p]:
            totals["shots"] += 1
            totals["shots_on_target"] += int(shot["on_target"] is True)
            totals["goals"] += int(shot["goal"] is True)
    team_path = _write_csv(
        ANALYTICS_DIR / f"team_shooting_stats{tag}.csv",
        [{"team_id": tid, **team_totals[tid]} for tid in ("team_a", "team_b")],
        ["team_id", "shots", "shots_on_target", "goals"],
    )
    player_path = _write_csv(
        ANALYTICS_DIR / f"player_shooting_stats{tag}.csv",
        [player_totals[sid] for sid in sorted(player_totals)],
        ["stable_id", "team_id", "shots", "shots_on_target", "goals"],
    )
    return team_path, player_path


def write_shot_validation_video(video_path, frame_state_csv, goals_csv, shots, output_path):
    """Goal boxes, ball and shot labels over the source video."""
    frame_df = pd.read_csv(frame_state_csv)
    balls = {
        int(r.frame): (int(r.ball_x), int(r.ball_y))
        for r in frame_df.itertuples(index=False)
        if str(r.ball_source).strip().lower() != "missing" and pd.notna(r.ball_x)
    }
    goals = load_goals(goals_csv) or {}
    shot_by_frame = {int(s["frame"]): s for s in shots}

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    min_frame, max_frame = int(frame_df["frame"].min()), int(frame_df["frame"].max())
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(min_frame - 1, 0))
    writer = cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        cap.release()
        raise RuntimeError(f"Cannot write video: {output_path}")

    label, until = None, -1
    for frame_index in range(min_frame, max_frame + 1):
        ok, image = cap.read()
        if not ok:
            break
        for x1, y1, x2, y2 in goals.get(frame_index, ()):
            cv2.rectangle(image, (int(x1), int(y1)), (int(x2), int(y2)), (255, 200, 0), 2)
        if frame_index in balls:
            cv2.circle(image, balls[frame_index], 8, (0, 255, 255), -1)
        if frame_index in shot_by_frame:
            s = shot_by_frame[frame_index]
            label = f"{s['outcome'].upper()}  id={s['shooter_stable_id']} {s['team_id']}  {s['confidence']}"
            until = frame_index + int(fps * 2)
        if label and frame_index <= until:
            cv2.putText(image, label, (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 255), 3, cv2.LINE_AA)
        writer.write(image)
    cap.release()
    writer.release()
    return output_path


def run_shot_detection(frame_state_csv, teams_csv, video_path, goals_csv, coordinate_csv=None, suffix=""):
    EVENTS_OUTPUT.mkdir(parents=True, exist_ok=True)
    ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)
    fps = _video_fps(video_path)
    tag = f"_{suffix}" if suffix else ""

    shots, validation, counts = detect_shots(frame_state_csv, teams_csv, fps, goals_csv, coordinate_csv)
    shots_path = _write_csv(EVENTS_OUTPUT / f"shots{tag}.csv", shots, SHOT_FIELDS)
    val_path = _write_csv(EVENTS_OUTPUT / f"shot_validation{tag}.csv", validation, VALIDATION_FIELDS)
    team_path, player_path = _write_shooting_stats(shots, suffix)

    video_out = None
    if WRITE_DEBUG_VIDEOS:
        video_out = EVENTS_OUTPUT / f"shot_validation{tag}.mp4"
        write_shot_validation_video(video_path, frame_state_csv, goals_csv, shots, video_out)

    by_team = {"team_a": 0, "team_b": 0}
    for s in shots:
        if s["team_id"] in by_team:
            by_team[s["team_id"]] += 1

    print("Shot detection (goals detected in video):")
    print(f"  FPS                 : {fps:.4f}")
    print(f"  confirmed intervals : {counts['confirmed_intervals']}")
    print(f"  shots               : {counts['confirmed_shots']} {by_team}")
    print(f"  shots on target     : {counts['shots_on_target']}")
    print(f"  goals               : {counts['goals']}")
    print(f"  rejection reasons   : {counts['rejected_reasons']}")
    print(f"  shots CSV           : {shots_path}")

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
    }
