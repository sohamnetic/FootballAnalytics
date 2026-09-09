from pathlib import Path
import cv2

from config.config import TEST_VIDEO
from scripts.analytics.motion_engine import MotionEngine
from scripts.analytics.heatmap import HeatmapEngine

csv = Path("outputs/coordinates/match_test.csv")

cap = cv2.VideoCapture(str(TEST_VIDEO))

ret, frame = cap.read()

fps = cap.get(cv2.CAP_PROP_FPS)

cap.release()

motion = MotionEngine(csv, fps)

trajectory = motion.get_smoothed_trajectory(1)

heatmap = HeatmapEngine(frame.shape)

heat = heatmap.generate(trajectory)

overlay = cv2.addWeighted(
    frame,
    0.55,
    heat,
    0.45,
    0
)

cv2.imshow("Heatmap", overlay)

cv2.waitKey(0)

cv2.destroyAllWindows()