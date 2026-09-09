from pathlib import Path
import cv2

from config.config import TEST_VIDEO
from scripts.analytics.motion_engine import MotionEngine

csv = Path("outputs/coordinates/match_test.csv")

cap = cv2.VideoCapture(str(TEST_VIDEO))
fps = cap.get(cv2.CAP_PROP_FPS)
cap.release()

motion = MotionEngine(csv, fps)

print("=" * 60)
print("ALL DETECTED PLAYERS")
print("=" * 60)

players = motion.get_all_players()

print(players)

print()

print("Total Players :", len(players))