"""
Where the goals are, frame by frame, for a panning/zooming camera.

A YOLO model fine-tuned on goal frames (posts + net; see
scripts/tools/label_goals.py and train_goal_detector.py) runs every
GOAL_DETECT_EVERY_S. Goals never move, so detections from the surrounding
GOAL_SMOOTH_WINDOW_S are carried into each frame through the camera
transforms and merged: one missed or spurious detection doesn't make a goal
blink in or out, and frames between detections still get a box.

Output (<coordinate stem>_goals.csv): frame, x1, y1, x2, y2, confidence,
support. A frame with no row has no goal in view.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from config.config import (
    GOAL_CONFIDENCE,
    GOAL_IMGSZ,
    GOAL_MIN_SUPPORT,
    GOAL_MODEL,
    GOAL_SMOOTH_WINDOW_S,
    GOAL_STRONG_CONFIDENCE,
)

COLUMNS = ["frame", "x1", "y1", "x2", "y2", "confidence", "support"]


def goals_path(coordinate_output):
    coordinate_output = Path(coordinate_output)
    return coordinate_output.with_name(f"{coordinate_output.stem}_goals.csv")


def goal_model_available():
    return Path(GOAL_MODEL).exists()


class GoalDetector:

    def __init__(self, device):
        from ultralytics import YOLO

        self.model = YOLO(str(GOAL_MODEL))
        self.device = device

    def detect(self, frame):
        result = self.model.predict(
            source=frame, conf=GOAL_CONFIDENCE, imgsz=GOAL_IMGSZ, device=self.device, verbose=False,
        )[0]
        if result.boxes is None:
            return []
        return [
            [*map(float, b.xyxy[0].tolist()), float(b.conf.item())]
            for b in result.boxes
        ]


def _map_boxes(boxes, t):
    """(n, 4) axis-aligned boxes through 3x3 similarity transforms."""
    x1, y1, x2, y2 = boxes.T
    corners = np.stack([
        np.stack([x1, y1], 1), np.stack([x2, y1], 1), np.stack([x1, y2], 1), np.stack([x2, y2], 1),
    ], 1)  # n, 4, 2
    pts = corners @ t[:2, :2].T + t[:2, 2]
    return np.concatenate([pts.min(1), pts.max(1)], 1)


def _iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def smooth_goals(detections, camera, fps, width, height):
    """
    detections: {frame: [[x1, y1, x2, y2, conf], ...]} on detection frames.
    camera: {frame: 3x3 transform, that frame's pixels -> first-frame pixels}.
    Returns rows for every tracked frame that has a goal in view.
    """
    det_frames = np.array(sorted(detections))
    if not len(det_frames):
        return []
    window = GOAL_SMOOTH_WINDOW_S * fps
    # detections in first-frame (stabilized) pixels
    stab = {}
    for f in det_frames:
        boxes = np.array(detections[f], float).reshape(-1, 5)
        if len(boxes):
            stab[f] = np.column_stack([_map_boxes(boxes[:, :4], camera[f]), boxes[:, 4]])

    rows = []
    for f in sorted(camera):
        lo = np.searchsorted(det_frames, f - window, side="left")
        hi = np.searchsorted(det_frames, f + window, side="right")
        near = [g for g in det_frames[lo:hi] if g in stab]
        if not near:
            continue
        # nearby detections into this frame's pixels (weight: closer in time)
        to_frame = np.linalg.inv(camera[f])
        cands = []
        for g in near:
            weight = 1.0 - abs(g - f) / (window + 1)
            for b in stab[g]:
                box = _map_boxes(b[None, :4], to_frame)[0]
                cands.append((box, b[4], weight, g))
        # group overlapping boxes (one group per physical goal)
        groups = []
        for box, conf, weight, g in sorted(cands, key=lambda c: -c[1] * c[2]):
            for grp in groups:
                if _iou(box, grp["boxes"][0]) >= 0.3:
                    grp["boxes"].append(box)
                    grp["w"].append(conf * weight)
                    grp["conf"].append(conf)
                    grp["frames"].add(g)
                    break
            else:
                groups.append({"boxes": [box], "w": [conf * weight], "conf": [conf], "frames": {g}})
        for grp in groups:
            support = len(grp["frames"])
            best = max(grp["conf"])
            if support < GOAL_MIN_SUPPORT and best < GOAL_STRONG_CONFIDENCE:
                continue
            w = np.array(grp["w"])
            box = (np.array(grp["boxes"]) * w[:, None]).sum(0) / w.sum()
            cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
            if not (0 <= cx < width and 0 <= cy < height):
                continue
            rows.append({
                "frame": int(f),
                "x1": round(float(box[0]), 1), "y1": round(float(box[1]), 1),
                "x2": round(float(box[2]), 1), "y2": round(float(box[3]), 1),
                "confidence": round(float(best), 3), "support": support,
            })
    return rows


def write_goals(rows, path):
    pd.DataFrame(rows, columns=COLUMNS).to_csv(path, index=False)
    return path


def load_goals(path):
    """{frame: [(x1, y1, x2, y2), ...]}"""
    path = Path(path)
    if not path.exists():
        return None
    df = pd.read_csv(path)
    out = {}
    for r in df.itertuples(index=False):
        out.setdefault(int(r.frame), []).append((r.x1, r.y1, r.x2, r.y2))
    return out
