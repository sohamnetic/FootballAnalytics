"""
0-10 player ratings from the actions we detect (like SofaScore / FotMob).

Everyone starts at RATING_BASE. Goals, shots and saves add a fixed amount
(a goal is a goal, however long the match). Passes, interceptions,
recoveries, time on the ball and losing the ball are scaled to "per 10
minutes on screen", with a few extra minutes added so a player seen for 30
seconds doesn't get a 9 from one lucky interception. Each rating keeps a
breakdown of what moved it, in rating points, so the dashboard can explain it.

Running (distance, sprints) isn't part of it yet.
"""
from __future__ import annotations

import pandas as pd

from config.config import (
    RATING_BASE,
    RATING_EVENT_POINTS,
    RATING_MIN_VISIBLE_S,
    RATING_ON_BALL_MAX,
    RATING_ON_BALL_PER_S,
    RATING_RATE_POINTS,
    RATING_SCALE,
    RATING_SHRINK_MIN,
)

LABELS = {
    "goal": "Goals",
    "shot_on_target": "Shots on target",
    "shot_off_target": "Other shots",
    "pass": "Passes",
    "pass_received": "Passes received",
    "interception": "Interceptions",
    "recovery": "Recoveries",
    "save": "Saves",
    "ball_lost": "Ball lost",
    "on_ball": "Time on the ball",
}


def _int(value):
    try:
        if value is None or value == "" or pd.isna(value):
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def visible_seconds(coordinate_csv, fps):
    """Seconds each player was on screen (frames with their id / fps)."""
    try:
        df = pd.read_csv(coordinate_csv, usecols=["frame", "stable_id", "class"])
    except (FileNotFoundError, ValueError, pd.errors.EmptyDataError):
        return {}
    df = df[(df["class"] == "person") & df["stable_id"].notna()]
    frames = df.groupby(df["stable_id"].astype(int))["frame"].nunique()
    return {int(sid): float(n) / fps for sid, n in frames.items()}


def goalkeepers(teams_df):
    if teams_df is None or teams_df.empty or "reason" not in teams_df.columns:
        return set()
    keep = teams_df["reason"].astype(str).str.startswith("goalkeeper")
    return {int(s) for s in teams_df.loc[keep, "stable_id"].dropna()}


def rate(counts, on_ball_s, visible_s):
    """Rating, confidence and breakdown for one player.

    counts: action -> number of times (keys of RATING_EVENT_POINTS and
    RATING_RATE_POINTS). Breakdown points are rating points."""
    minutes = max(visible_s, 0.0) / 60.0
    per_point = RATING_SCALE * 10.0 / (minutes + RATING_SHRINK_MIN)
    items = []
    for action, weight in RATING_EVENT_POINTS.items():
        n = int(counts.get(action) or 0)
        if n:
            items.append((action, n, n * weight))
    for action, weight in RATING_RATE_POINTS.items():
        n = int(counts.get(action) or 0)
        if n:
            items.append((action, n, n * weight * per_point))
    on_ball = min(on_ball_s * RATING_ON_BALL_PER_S, RATING_ON_BALL_MAX)
    if on_ball > 0:
        items.append(("on_ball", round(on_ball_s, 1), on_ball * per_point))

    breakdown = [
        {"key": key, "label": LABELS[key], "count": count, "points": round(points, 2)}
        for key, count, points in items
    ]
    breakdown.sort(key=lambda b: -abs(b["points"]))
    raw = RATING_BASE + sum(points for _, _, points in items)
    rating = round(min(10.0, max(3.0, raw)), 1)
    confidence = "low" if visible_s < RATING_MIN_VISIBLE_S else "normal"
    return rating, confidence, breakdown


def add_ratings(players, *, passes_df, intercepts_df, shots_df, teams_df, coordinate_csv, fps):
    """Adds rating fields to each player dict (keyed by stable_id) and
    returns the player of the match id (or None)."""
    received, lost, saves = {}, {}, {}
    shot_counts = {sid: {"goal": 0, "shot_on_target": 0, "shot_off_target": 0} for sid in players}

    if passes_df is not None and not passes_df.empty and "receiver_stable_id" in passes_df.columns:
        for sid in passes_df["receiver_stable_id"].map(_int):
            if sid is not None:
                received[sid] = received.get(sid, 0) + 1

    if intercepts_df is not None and not intercepts_df.empty and "opponent_stable_id" in intercepts_df.columns:
        for sid in intercepts_df["opponent_stable_id"].map(_int):
            if sid is not None:
                lost[sid] = lost.get(sid, 0) + 1

    keepers = goalkeepers(teams_df)
    if shots_df is not None and not shots_df.empty:
        for _, row in shots_df.iterrows():
            sid = _int(row.get("shooter_stable_id"))
            outcome = str(row.get("outcome") or "").strip().lower()
            if not outcome:  # older shots files
                goal = str(row.get("goal")).lower() == "true"
                outcome = "goal" if goal else ("on_target" if str(row.get("on_target")).lower() == "true" else "off_target")
            if sid in shot_counts:
                key = {"goal": "goal", "saved": "shot_on_target", "on_target": "shot_on_target"}.get(outcome, "shot_off_target")
                shot_counts[sid][key] += 1
            stopper = _int(row.get("stopped_by_stable_id"))
            if outcome == "saved" and stopper in keepers:
                saves[stopper] = saves.get(stopper, 0) + 1

    seen = visible_seconds(coordinate_csv, fps) if coordinate_csv else {}
    best, best_rating = None, None
    for sid, p in players.items():
        counts = {
            **shot_counts[sid],
            "pass": p.get("successful_passes") or 0,
            "pass_received": received.get(sid, 0),
            "interception": p.get("interceptions") or 0,
            "recovery": p.get("ball_recoveries") or 0,
            "save": saves.get(sid, 0),
            "ball_lost": lost.get(sid, 0),
        }
        visible = seen.get(sid, 0.0)
        rating, confidence, breakdown = rate(counts, p.get("ball_possession_time_seconds") or 0.0, visible)
        p.update(
            rating=rating,
            rating_confidence=confidence,
            rating_breakdown=breakdown,
            visible_seconds=round(visible, 1),
            passes_received=counts["pass_received"],
            ball_losses=counts["ball_lost"],
            saves=counts["save"],
            is_goalkeeper=sid in keepers,
        )
        if confidence == "normal" and (best_rating is None or rating > best_rating):
            best, best_rating = sid, rating
    return best
