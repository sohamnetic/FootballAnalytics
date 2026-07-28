from ultralytics import YOLO
from pathlib import Path
import time

from config.config import (
    YOLO_MODEL,
    TEST_VIDEO,
    TRACKER_CONFIG,
    TRACKING_OUTPUT,
    PROJECT_ROOT
)

from scripts.coordinate_logger import CoordinateLogger

# ======================================================
# OUTPUT PATHS
# ======================================================

COORDINATE_OUTPUT = (
    PROJECT_ROOT /
    "outputs" /
    "coordinates" /
    "match_test.csv"
)

# ======================================================

print("=" * 60)
print("Football Analytics - Player Tracking")
print("=" * 60)

print("\nLoading YOLO model...")

model = YOLO(YOLO_MODEL)

print("Model loaded successfully!")

logger = CoordinateLogger(COORDINATE_OUTPUT)

start = time.time()

results = model.track(

    source=str(TEST_VIDEO),

    tracker=str(TRACKER_CONFIG),

    persist=True,

    save=True,

    stream=True,

    device=0,

    imgsz=1280,

    conf=0.30,

    project=str(TRACKING_OUTPUT),

    name="match_tracking",

    exist_ok=True,

    verbose=False

)

frame_count = 0

for result in results:

    frame_count += 1

    if result.boxes is not None:

        for box in result.boxes:

            # Skip if no Track ID
            if box.id is None:
                continue

            track_id = int(box.id.item())

            cls = int(box.cls.item())

            cls_name = model.names[cls]

            confidence = float(box.conf.item())

            x1, y1, x2, y2 = map(int, box.xyxy[0])

            logger.log(

                frame_number=frame_count,

                track_id=track_id,

                cls_name=cls_name,

                confidence=round(confidence, 4),

                x1=x1,

                y1=y1,

                x2=x2,

                y2=y2

            )

    if frame_count % 500 == 0:

        print(f"Processed {frame_count} frames")

logger.close()

end = time.time()

print("\n" + "=" * 60)
print("Tracking Finished!")
print("=" * 60)

print(f"Frames Processed : {frame_count}")
print(f"Time Taken : {end-start:.2f} seconds")

print("\nTracking Output:")
print(TRACKING_OUTPUT / "match_tracking")

print("\nCoordinate File:")
print(COORDINATE_OUTPUT)