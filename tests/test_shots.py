"""
Tests for shot/goal detection using made-up data (no video needed).
The camera pans the whole time, so everything moves across the image.

  python -m pytest tests/test_shots.py
  python -m tests.test_shots
"""
import tempfile
from pathlib import Path

import pandas as pd

from scripts.analytics.events.shots import detect_shots

FPS = 30.0
PAN_PX_PER_FRAME = 3.0
GOAL = (1500, 300, 1700, 450)
SHOOTER_FEET = (1100, 700)
TEAMMATE_FEET = (900, 600)
KEEPER_BOX = (1560, 250, 1620, 420)
TARGETS = {                            # where the ball ends up
    "goal": (1660, 330),
    "wide": (1850, 470),
    "save": (1590, 400),
    "pass": (900, 595),
}


def _person(frame, sid, x1, y1, x2, y2):
    return {"frame": frame, "track_id": sid, "stable_id": sid, "class": "person", "confidence": 0.9,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2, "center_x": (x1 + x2) / 2, "center_y": y2}


def _scene(kind, folder):
    """Player 1 has the ball for 40 frames and then kicks it."""
    states, people, goals = [], [], []
    tx, ty = TARGETS[kind]
    for f in range(1, 151):
        s = -PAN_PX_PER_FRAME * f
        gx1, gy1, gx2, gy2 = GOAL
        goals.append({"frame": f, "x1": gx1 + s, "y1": gy1, "x2": gx2 + s, "y2": gy2,
                      "confidence": 0.9, "support": 5})
        px, py = SHOOTER_FEET
        mx, my = TEAMMATE_FEET
        kx1, ky1, kx2, ky2 = KEEPER_BOX
        people += [
            _person(f, 1, px - 30 + s, py - 180, px + 30 + s, py),
            _person(f, 2, mx - 30 + s, my - 180, mx + 30 + s, my),
            _person(f, 3, kx1 + s, ky1, kx2 + s, ky2),
        ]
        state, possessor = "loose", ""
        if f <= 40:
            bx, by = px + 10, py - 5
            state, possessor = "confirmed", 1
        else:
            k = min(1.0, (f - 40) / 20)
            bx, by = px + 10 + (tx - px - 10) * k, py - 5 + (ty - py + 5) * k
            if kind == "save" and k >= 1.0:
                state, possessor = "confirmed", 3
            if kind == "pass" and k >= 1.0:
                state, possessor = "confirmed", 2
        states.append({"frame": f, "time_s": (f - 1) / FPS, "ball_x": bx + s, "ball_y": by,
                       "ball_source": "detected", "ball_confidence": 0.5,
                       "nearest_player_stable_id": possessor, "nearest_player_distance_px": 10,
                       "possessor_stable_id": possessor, "possession_state": state})
    folder = Path(folder)
    pd.DataFrame(states).to_csv(folder / "frame_state.csv", index=False)
    pd.DataFrame(people).to_csv(folder / "coords.csv", index=False)
    pd.DataFrame(goals).to_csv(folder / "goals.csv", index=False)
    pd.DataFrame([
        {"stable_id": 1, "team_id": "team_a"},
        {"stable_id": 2, "team_id": "team_a"},
        {"stable_id": 3, "team_id": "team_b"},
    ]).to_csv(folder / "teams.csv", index=False)
    shots, _, _ = detect_shots(
        folder / "frame_state.csv", folder / "teams.csv", FPS, folder / "goals.csv", folder / "coords.csv",
    )
    return shots


def _outcome(kind):
    with tempfile.TemporaryDirectory() as d:
        shots = _scene(kind, d)
    return [s["outcome"] for s in shots]


def test_ball_into_the_net_is_a_goal():
    assert _outcome("goal") == ["goal"]


def test_ball_past_the_post_is_an_attempt():
    assert _outcome("wide") == ["off_target"]


def test_keeper_save_is_on_target():
    assert _outcome("save") == ["saved"]


def test_pass_to_teammate_is_not_a_shot():
    assert _outcome("pass") == []


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
