"""
Re-run goal detection for an existing coordinate CSV (no re-tracking), e.g.
after retraining the goal model. Writes <coordinate stem>_goals.csv, the same
file scripts/track.py produces.

  python -m scripts.tools.detect_goals --video data/uploads/<id>/video.mp4 \
      --csv outputs/matches/<id>/coordinates/video.csv
"""
import argparse
import time

import cv2
import pandas as pd

from config.config import DEVICE, GOAL_DETECT_EVERY_S
from scripts.vision.camera_motion import CameraMotion
from scripts.vision.goals import GoalDetector, goals_path, smooth_goals, write_goals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--csv", required=True)
    args = ap.parse_args()

    df = pd.read_csv(args.csv)
    people = df[df["class"] == "person"]
    boxes = {f: g[["x1", "y1", "x2", "y2"]].to_numpy() for f, g in people.groupby("frame")}
    first, last = int(df["frame"].min()), int(df["frame"].max())

    cap = cv2.VideoCapture(args.video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.set(cv2.CAP_PROP_POS_FRAMES, first - 1)
    every = max(1, int(round(GOAL_DETECT_EVERY_S * fps)))

    detector, camera = GoalDetector(DEVICE), CameraMotion()
    transforms, detections = {}, {}
    t0 = time.time()
    for frame_no in range(first, last + 1):
        ok, frame = cap.read()
        if not ok:
            break
        transforms[frame_no] = camera.update(frame, boxes.get(frame_no, []))
        if (frame_no - first) % every == 0:
            detections[frame_no] = detector.detect(frame)
    cap.release()

    rows = smooth_goals(detections, transforms, fps, width, height)
    path = write_goals(rows, goals_path(args.csv))
    print(f"goals in view on {len({r['frame'] for r in rows})}/{len(transforms)} frames "
          f"({time.time() - t0:.0f}s) -> {path}")


if __name__ == "__main__":
    main()
