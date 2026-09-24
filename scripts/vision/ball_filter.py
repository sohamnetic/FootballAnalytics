"""
Pick the real ball out of YOLO "sports ball" candidates.

The detector runs at a low confidence threshold (small indoor ball), so each
frame can carry fixed look-alikes: a white fitting on the wall netting, a
round sign by the bench, a whistle. The fitting scores up to 0.6 and used to
beat the real ball whenever both were in view.

Rules, applied after tracking so the whole clip is known:
  1. Static objects are rejected. An off-turf candidate that stays at the same
     camera-compensated position for a while is a fixture, not a ball in
     flight (a real ball off the turf is in the air and moving). On the turf
     the bar is higher, since a real ball can rest before a restart: a water
     bottle or cap left by the goal stays put for much longer.
  2. Remaining off-turf candidates need BALL_OFF_TURF_MIN_CONF.
  3. Per frame, the best score wins, with a small preference for candidates
     on the turf.
"""
import cv2
import numpy as np

from config.config import BALL_OFF_TURF_MIN_CONF
from scripts.vision.turf import turf_mask

_ON_TURF = 0.2            # turf fraction around the ball
_STATIC_RADIUS_PX = 30.0  # compensated positions this close = "didn't move"
_STATIC_MIN_S = 1.0       # ...for at least this much time (off the turf)
_STATIC_WINDOW_S = 4.0
_STATIC_ON_TURF_MIN_S = 4.0
_STATIC_ON_TURF_WINDOW_S = 10.0
_TURF_PREFERENCE = 0.15


def ring_turf_fraction(frame_bgr, x1, y1, x2, y2):
    """Share of turf pixels in a square around the ball (2.5 ball widths)."""
    h, w = frame_bgr.shape[:2]
    size = max(x2 - x1, y2 - y1, 6)
    cx, cy, r = (x1 + x2) // 2, (y1 + y2) // 2, int(2.5 * size)
    patch = frame_bgr[max(0, cy - r):min(h, cy + r), max(0, cx - r):min(w, cx + r)]
    if patch.size == 0:
        return 0.0
    return float(turf_mask(cv2.cvtColor(patch, cv2.COLOR_BGR2HSV).reshape(-1, 3)).mean())


def _static(idx, frames, stab, window, need):
    """Candidates in idx that sit at one compensated position for `need`
    frames (half of them detected) within +-window frames."""
    static = np.zeros(len(frames), bool)
    idx = idx[np.argsort(frames[idx], kind="stable")]
    sorted_frames = frames[idx]
    los = np.searchsorted(sorted_frames, sorted_frames - window, side="left")
    his = np.searchsorted(sorted_frames, sorted_frames + window, side="right")
    for i, lo, hi in zip(idx, los, his):
        near = idx[lo:hi]
        close = near[np.linalg.norm(stab[near] - stab[i], axis=1) <= _STATIC_RADIUS_PX]
        span = frames[close].max() - frames[close].min()
        if len(np.unique(frames[close])) >= need * 0.5 and span >= need:
            static[i] = True
    return static


def select_balls(candidates, camera, fps):
    """
    candidates: list of dicts frame, confidence, x1, y1, x2, y2, turf.
    camera: {frame: 3x3 transform to first-frame pixels}.
    Returns ({frame: chosen candidate}, stats).
    """
    if not candidates:
        return {}, {"candidates": 0, "static_rejected": 0, "low_conf_off_turf": 0, "frames_with_ball": 0}

    frames = np.array([c["frame"] for c in candidates])
    conf = np.array([c["confidence"] for c in candidates], float)
    turf = np.array([c["turf"] for c in candidates], float)
    centres = np.array([[(c["x1"] + c["x2"]) / 2, (c["y1"] + c["y2"]) / 2, 1.0] for c in candidates])
    stab = np.array([camera.get(int(f), np.eye(3)) @ p for f, p in zip(frames, centres)])[:, :2]

    off = turf < _ON_TURF
    static = np.zeros(len(candidates), bool)
    for group, window_s, min_s in (
        (off, _STATIC_WINDOW_S, _STATIC_MIN_S),
        (~off, _STATIC_ON_TURF_WINDOW_S, _STATIC_ON_TURF_MIN_S),
    ):
        static |= _static(np.flatnonzero(group), frames, stab, window_s * fps, min_s * fps)

    weak_off = off & ~static & (conf < BALL_OFF_TURF_MIN_CONF)
    keep = ~static & ~weak_off
    score = conf + _TURF_PREFERENCE * (~off)

    chosen = {}
    for i in np.flatnonzero(keep):
        f = int(frames[i])
        if f not in chosen or score[i] > chosen[f][0]:
            chosen[f] = (score[i], candidates[i])
    stats = {
        "candidates": len(candidates),
        "static_rejected": int(static.sum()),
        "low_conf_off_turf": int(weak_off.sum()),
        "frames_with_ball": len(chosen),
    }
    return {f: c for f, (_, c) in chosen.items()}, stats
