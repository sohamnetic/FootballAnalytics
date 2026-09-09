from pathlib import Path
import cv2

from config.config import TEST_VIDEO
from scripts.analytics.motion_engine import MotionEngine

csv = Path("outputs/coordinates/match_test.csv")

cap = cv2.VideoCapture(str(TEST_VIDEO))
fps = cap.get(cv2.CAP_PROP_FPS)
cap.release()

motion = MotionEngine(csv, fps)

print("=" * 50)
print("Motion Engine Test")
print("=" * 50)

print()

print("Trajectory Points :", len(motion.get_trajectory(1)))

print()

print("Distance :", round(motion.get_distance(1), 2))

speeds = motion.get_speed(1)

print()

print("Average Speed :", round(sum(speeds) / len(speeds), 2))

print("Maximum Speed :", round(max(speeds), 2))