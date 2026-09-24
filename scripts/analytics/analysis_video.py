"""
Makes the "Tracking" video for the dashboard.

Draws players (in their team colour, with the same ids as the stats page),
the ball, the goals, who has the ball, possession so far and captions for
passes/shots/etc on top of the match.

We pipe frames into ffmpeg to get H.264, because the mp4 files OpenCV
writes don't play in browsers. No ffmpeg = no video.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from config.config import (
    ANALYSIS_VIDEO_CRF,
    ANALYSIS_VIDEO_PRESET,
    ANALYSIS_VIDEO_WIDTH,
    FFMPEG_BIN,
)
from scripts.vision.goals import load_goals

REFEREE_BGR = (40, 215, 245)
UNKNOWN_BGR = (170, 170, 170)
WHITE = (255, 255, 255)
BALL_BGR = (255, 255, 255)
CAPTION_S = 2.0
FONT = cv2.FONT_HERSHEY_DUPLEX


def ffmpeg_path():
    return FFMPEG_BIN or shutil.which("ffmpeg")


def _events(events_dir, tag):
    """All events as (frame, caption, team), sorted."""
    out = []

    def rows(name):
        path = Path(events_dir) / f"{name}{tag}.csv"
        if not path.exists():
            return []
        df = pd.read_csv(path)
        return [] if df.empty else df.to_dict("records")

    for r in rows("passes"):
        out.append((int(r["frame"]), f"PASS  {int(r['passer_stable_id'])} > {int(r['receiver_stable_id'])}", r["team_id"]))
    for r in rows("interceptions"):
        out.append((int(r["frame"]), f"INTERCEPTION  by {int(r['interceptor_stable_id'])}", r["team_id"]))
    for r in rows("recoveries"):
        out.append((int(r["frame"]), f"BALL RECOVERY  by {int(r['player_stable_id'])}", r["team_id"]))
    for r in rows("shots"):
        outcome = str(r.get("outcome", "")).replace("_", " ").upper()
        label = "GOAL!" if str(r.get("goal")).lower() == "true" else f"SHOT  {outcome}"
        out.append((int(r["frame"]), f"{label}  by {int(r['shooter_stable_id'])}", r["team_id"]))
    return sorted(out)


def _label(img, text, x, y, bg, scale, thick=1, pad=4):
    """Draw a small label above (x, y)."""
    (w, h), base = cv2.getTextSize(text, FONT, scale, thick)
    x1, y1 = int(x - w / 2 - pad), int(y - h - base - 2 * pad)
    x2, y2 = int(x + w / 2 + pad), int(y)
    cv2.rectangle(img, (x1, y1), (x2, y2), bg, -1, cv2.LINE_AA)
    lum = 0.114 * bg[0] + 0.587 * bg[1] + 0.299 * bg[2]
    cv2.putText(img, text, (x1 + pad, y2 - pad - base + 1), FONT, scale, (20, 20, 20) if lum > 150 else WHITE,
                thick, cv2.LINE_AA)


def render_analysis_video(
    video_path,
    coordinate_csv,
    frame_state_csv,
    teams_csv,
    goals_csv,
    events_dir,
    output_path,
    team_colors,
    tag="",
):
    """Returns the output path, or None if it couldn't be made."""
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        print("Analysis video skipped: ffmpeg not found (set FA_FFMPEG or add ffmpeg to PATH).")
        return None

    coords = pd.read_csv(coordinate_csv)
    people = coords[coords["class"] == "person"]
    by_frame = {int(f): g[["stable_id", "x1", "y1", "x2", "y2"]].to_numpy() for f, g in people.groupby("frame")}
    fs = pd.read_csv(frame_state_csv)
    state_of = {int(r.frame): r for r in fs.itertuples(index=False)}
    teams = {}
    if Path(teams_csv).exists():
        t = pd.read_csv(teams_csv)
        teams = dict(zip(t["stable_id"].astype(int), t["team_id"]))
    goals = load_goals(goals_csv) or {}
    events = _events(events_dir, tag)

    def color_of(sid):
        team = teams.get(int(sid))
        if team in team_colors:
            return team_colors[team]
        return REFEREE_BGR if team == "referee" else UNKNOWN_BGR

    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    src_w, src_h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    out_w = min(ANALYSIS_VIDEO_WIDTH, src_w) // 2 * 2
    out_h = int(round(src_h * out_w / src_w)) // 2 * 2
    s = out_w / src_w
    first, last = int(fs["frame"].min()), int(fs["frame"].max())
    cap.set(cv2.CAP_PROP_POS_FRAMES, first - 1)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_suffix(".part.mp4")
    proc = subprocess.Popen(
        [ffmpeg, "-y", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{out_w}x{out_h}", "-r", f"{fps:.6f}", "-i", "-",
         "-an", "-c:v", "libx264", "-preset", ANALYSIS_VIDEO_PRESET, "-crf", str(ANALYSIS_VIDEO_CRF),
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(tmp)],
        stdin=subprocess.PIPE,
    )

    tag_scale = 0.42 * out_w / 1280
    hud_scale = 0.55 * out_w / 1280
    held = {"team_a": 0, "team_b": 0}
    caption, caption_until, caption_team = None, -1, None
    ev_i = 0
    written = 0
    try:
        for frame_no in range(first, last + 1):
            ok, img = cap.read()
            if not ok:
                break
            img = cv2.resize(img, (out_w, out_h), interpolation=cv2.INTER_AREA)
            state = state_of.get(frame_no)
            possessor = None
            if state is not None and state.possession_state == "confirmed" and pd.notna(state.possessor_stable_id):
                possessor = int(state.possessor_stable_id)
                team = teams.get(possessor)
                if team in held:
                    held[team] += 1

            overlay = img.copy()
            for x1, y1, x2, y2 in goals.get(frame_no, ()):
                cv2.rectangle(overlay, (int(x1 * s), int(y1 * s)), (int(x2 * s), int(y2 * s)), WHITE, 2, cv2.LINE_AA)
            # rings under the players (a bit transparent)
            for sid, x1, y1, x2, y2 in by_frame.get(frame_no, ()):
                if pd.isna(sid):
                    continue
                cx, fy, w = (x1 + x2) / 2 * s, y2 * s, (x2 - x1) * s
                cv2.ellipse(overlay, (int(cx), int(fy)), (max(8, int(w * 0.55)), max(3, int(w * 0.18))),
                            0, 0, 360, color_of(sid), 3 if int(sid) == possessor else 2, cv2.LINE_AA)
            img = cv2.addWeighted(overlay, 0.75, img, 0.25, 0)

            for sid, x1, y1, x2, y2 in by_frame.get(frame_no, ()):
                if pd.isna(sid):
                    continue
                cx, top = (x1 + x2) / 2 * s, y1 * s
                _label(img, str(int(sid)), cx, top - 3, color_of(sid), tag_scale)
                if int(sid) == possessor:
                    ty = top - 22 * out_w / 1280
                    tri = np.array([[cx - 7, ty - 10], [cx + 7, ty - 10], [cx, ty]], np.int32)
                    cv2.fillPoly(img, [tri], WHITE, cv2.LINE_AA)

            if state is not None and pd.notna(state.ball_x) and state.ball_source != "missing":
                bx, by = int(state.ball_x * s), int(state.ball_y * s)
                r = max(5, int(7 * out_w / 1280))
                if state.ball_source == "detected":
                    cv2.circle(img, (bx, by), r, BALL_BGR, -1, cv2.LINE_AA)
                    cv2.circle(img, (bx, by), r + 2, (30, 30, 30), 2, cv2.LINE_AA)
                else:
                    cv2.circle(img, (bx, by), r, BALL_BGR, 2, cv2.LINE_AA)

            while ev_i < len(events) and events[ev_i][0] <= frame_no:
                _, caption, caption_team = events[ev_i]
                caption_until = frame_no + int(CAPTION_S * fps)
                ev_i += 1

            # clock + possession box, top left
            secs = (frame_no - 1) / fps
            pad = int(12 * out_w / 1280)
            bar_w, bar_h = int(220 * out_w / 1280), int(8 * out_w / 1280)
            box = img[pad:pad + int(54 * out_w / 1280), pad:pad + bar_w + 2 * pad]
            box[:] = (box * 0.35).astype(np.uint8)
            cv2.putText(img, f"{int(secs // 60):02d}:{int(secs % 60):02d}", (2 * pad, pad + int(24 * out_w / 1280)),
                        FONT, hud_scale, WHITE, 1, cv2.LINE_AA)

            total = held["team_a"] + held["team_b"]
            share = held["team_a"] / total if total else 0.5
            color_a = team_colors.get("team_a", UNKNOWN_BGR)
            color_b = team_colors.get("team_b", UNKNOWN_BGR)
            bx0, bx1, by0 = 2 * pad, pad + bar_w, pad + int(36 * out_w / 1280)
            split = bx0 + int((bx1 - bx0) * share)
            cv2.rectangle(img, (bx0, by0), (split, by0 + bar_h), color_a, -1)
            cv2.rectangle(img, (split, by0), (bx1, by0 + bar_h), color_b, -1)
            text_y = pad + int(24 * out_w / 1280)
            right = f"{(1 - share) * 100:.0f}%"
            (rw, _), _ = cv2.getTextSize(right, FONT, hud_scale * 0.8, 1)
            cv2.putText(img, right, (bx1 - rw, text_y), FONT, hud_scale * 0.8, color_b, 1, cv2.LINE_AA)
            left = f"{share * 100:.0f}%"
            (lw, _), _ = cv2.getTextSize(left, FONT, hud_scale * 0.8, 1)
            cv2.putText(img, left, (bx1 - rw - lw - int(10 * out_w / 1280), text_y), FONT, hud_scale * 0.8,
                        color_a, 1, cv2.LINE_AA)

            if caption and frame_no <= caption_until:
                col = team_colors.get(caption_team, UNKNOWN_BGR)
                _label(img, caption, out_w / 2, out_h - pad * 2, col, hud_scale * 1.2, thick=1, pad=10)

            proc.stdin.write(img.tobytes())
            written += 1
    finally:
        cap.release()
        proc.stdin.close()
        code = proc.wait()
    if code != 0 or written == 0:
        tmp.unlink(missing_ok=True)
        print(f"Analysis video failed (ffmpeg exit {code}, {written} frames).")
        return None
    tmp.replace(output_path)
    return output_path
