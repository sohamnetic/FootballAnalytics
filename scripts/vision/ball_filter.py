"""
Pick the real ball out of the "sports ball" detections.

We run the ball detector with a low threshold, so it also finds things that
look like a ball (a white fitting on the netting, a water bottle behind the
goal...). Those never move, so:

1. anything that stays in the same place for a while is thrown out
   (1 s off the turf, 4 s on it - a real ball can sit still before a restart)
2. off the turf we need a higher confidence
3. per frame, highest score wins (small bonus for being on the turf)
"""
import cv2
import numpy as np

from config.config import BALL_OFF_TURF_MIN_CONF
from scripts.vision.turf import turf_mask

_ON_TURF = 0.2            # turf share around the ball
_STATIC_RADIUS_PX = 30.0  # closer than this = didn't move
_STATIC_MIN_S = 1.0
_STATIC_WINDOW_S = 4.0
_STATIC_ON_TURF_MIN_S = 4.0
_STATIC_ON_TURF_WINDOW_S = 10.0
_TURF_PREFERENCE = 0.15


def ring_turf_fraction(frame_bgr, x1, y1, x2, y2):
    """How much of the area around the ball is turf."""
    h, w = frame_bgr.shape[:2]
    size = max(x2 - x1, y2 - y1, 6)
    cx, cy, r = (x1 + x2) // 2, (y1 + y2) // 2, int(2.5 * size)
    patch = frame_bgr[max(0, cy - r):min(h, cy + r), max(0, cx - r):min(w, cx + r)]
    if patch.size == 0:
        return 0.0
    return float(turf_mask(cv2.cvtColor(patch, cv2.COLOR_BGR2HSV).reshape(-1, 3)).mean())


def _static(idx, frames, stab, window, need):
    """Mark candidates that sit in one spot for at least `need` frames."""
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
    """Returns ({frame: best candidate}, stats)."""
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
