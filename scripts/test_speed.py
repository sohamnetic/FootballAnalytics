from pathlib import Path

from scripts.analytics.speed import SpeedEngine
from config.config import TEST_VIDEO
import cv2

csv = Path("outputs/coordinates/match_test.csv")

cap = cv2.VideoCapture(str(TEST_VIDEO))

fps = cap.get(cv2.CAP_PROP_FPS)

cap.release()

engine = SpeedEngine(csv, fps)

speeds = engine.calculate_speed(1)

print("=" * 40)
print("Player 1 Speed")
print("=" * 40)

print(f"Frames Analysed : {len(speeds)}")
print(f"Average Speed   : {sum(speeds)/len(speeds):.2f} px/s")
print(f"Maximum Speed   : {max(speeds):.2f} px/s")

print("\nFirst 10 Speeds")

for s in speeds[:10]:
    print(f"{s:.2f}")