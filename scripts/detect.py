from ultralytics import YOLO
from pathlib import Path
import time

# ======================================================
# PATHS
# ======================================================

MODEL_PATH = r"D:\FootballAnalytics\models\yolo11n.pt"

VIDEO_PATH = r"D:\FootballAnalytics\videos\test\match_test.mp4"

OUTPUT_DIR = r"D:\FootballAnalytics\outputs\detections"

# ======================================================

print("=" * 60)
print("Football Analytics - Player Detection")
print("=" * 60)

# Load YOLO model
print("\nLoading YOLO model...")
model = YOLO(MODEL_PATH)
print("Model loaded successfully!")

# Start timer
start_time = time.time()

print("\nStarting detection...\n")

results = model.predict(
    source=VIDEO_PATH,

    # GPU
    device=0,

    # Save annotated video
    save=True,

    # Output location
    project=OUTPUT_DIR,
    name="match_test",

    exist_ok=True,

    # VERY IMPORTANT
    stream=True,

    # Football-friendly settings
    imgsz=1280,
    conf=0.30,

    verbose=False
)

frame_count = 0

for _ in results:
    frame_count += 1

    if frame_count % 500 == 0:
        print(f"Processed {frame_count} frames...")

end_time = time.time()

print("\n" + "=" * 60)
print("Detection Finished!")
print("=" * 60)

print(f"Frames Processed : {frame_count}")
print(f"Time Taken       : {end_time-start_time:.2f} seconds")

print("\nAnnotated video saved inside:")

print(Path(OUTPUT_DIR) / "match_test")