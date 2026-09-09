import cv2

from ultralytics import YOLO

from scripts.vision.jersey_color import JerseyColorExtractor
from config.config import TEST_VIDEO, YOLO_MODEL

cap = cv2.VideoCapture(str(TEST_VIDEO))

ret, frame = cap.read()

cap.release()

if not ret:
    print("Could not read video.")
    exit()

model = YOLO(str(YOLO_MODEL))

results = model(frame, verbose=False)

extractor = JerseyColorExtractor()

for box in results[0].boxes:

    cls = int(box.cls.item())

    if model.names[cls] != "person":
        continue

    x1, y1, x2, y2 = map(int, box.xyxy[0])

    color = extractor.extract_color(
        frame,
        (x1, y1, x2, y2)
    )

    print(color)

    cv2.rectangle(
        frame,
        (x1, y1),
        (x2, y2),
        (0,255,0),
        2
    )

cv2.imshow("Players", frame)

cv2.waitKey(0)

cv2.destroyAllWindows()