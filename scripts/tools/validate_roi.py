import json
from pathlib import Path

import cv2
import numpy as np

from config.config import OUTPUT_DIR, PROJECT_ROOT, TEST_VIDEO

ROI_FILE = PROJECT_ROOT / "data" / "roi" / "camera_001.json"
OUTPUT_FOLDER = OUTPUT_DIR / "roi_validation"
OUTPUT_IMAGE = OUTPUT_FOLDER / "camera_001_roi_validation.png"

CORNER_LABELS = ["TL", "TR", "BR", "BL"]


def load_roi(roi_path: Path):
    with open(roi_path, encoding="utf-8") as f:
        data = json.load(f)

    corners = data.get("corners")
    if not isinstance(corners, list) or len(corners) != 4:
        raise ValueError(
            f"ROI must contain exactly 4 corners, found: {corners!r}"
        )

    points = []
    for i, corner in enumerate(corners):
        if not isinstance(corner, (list, tuple)) or len(corner) != 2:
            raise ValueError(f"Corner {i + 1} is not an [x, y] pair: {corner!r}")
        points.append((int(corner[0]), int(corner[1])))

    return data, points


def validate_points(points, width, height):
    for i, (x, y) in enumerate(points, start=1):
        if not (0 <= x < width and 0 <= y < height):
            raise ValueError(
                f"Corner {i} ({x}, {y}) is outside the frame "
                f"{width}x{height}"
            )

    polygon = np.array(points, dtype=np.int32).reshape((-1, 1, 2))
    area = abs(float(cv2.contourArea(polygon)))
    if area <= 0:
        raise ValueError("ROI polygon has zero area")

    return area


def draw_roi(frame, points):
    canvas = frame.copy()
    pts = np.array(points, dtype=np.int32)

    overlay = canvas.copy()
    cv2.fillPoly(overlay, [pts], (0, 80, 0))
    canvas = cv2.addWeighted(overlay, 0.25, canvas, 0.75, 0)

    cv2.polylines(canvas, [pts], True, (0, 255, 0), 3)

    for i, (x, y) in enumerate(points):
        number = str(i + 1)
        label = CORNER_LABELS[i]

        cv2.circle(canvas, (x, y), 10, (0, 0, 255), -1)
        cv2.circle(canvas, (x, y), 12, (255, 255, 255), 2)

        number_org = (x + 16, y - 16)
        label_org = (x + 16, y + 18)

        cv2.putText(
            canvas, number, number_org,
            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 4, cv2.LINE_AA
        )
        cv2.putText(
            canvas, number, number_org,
            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA
        )
        cv2.putText(
            canvas, label, label_org,
            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 4, cv2.LINE_AA
        )
        cv2.putText(
            canvas, label, label_org,
            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2, cv2.LINE_AA
        )

    return canvas


def main():
    video_path = Path(TEST_VIDEO)
    roi_path = ROI_FILE

    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not roi_path.exists():
        raise FileNotFoundError(f"ROI file not found: {roi_path}")

    cap = cv2.VideoCapture(str(video_path))
    ret, frame = cap.read()
    cap.release()

    if not ret:
        raise RuntimeError(f"Cannot read first frame: {video_path}")

    height, width = frame.shape[:2]
    roi_data, points = load_roi(roi_path)
    area = validate_points(points, width, height)

    canvas = draw_roi(frame, points)

    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(OUTPUT_IMAGE), canvas):
        raise RuntimeError(f"Failed to write: {OUTPUT_IMAGE}")

    print("=" * 60)
    print("ROI validation")
    print("=" * 60)
    print(f"Video path       : {video_path}")
    print(f"Frame resolution : {width} x {height}")
    print(f"ROI JSON         : {roi_path}")
    print(f"Camera name      : {roi_data.get('camera_name', '')}")
    print("Corners (intended TL, TR, BR, BL):")
    for i, (x, y) in enumerate(points):
        print(f"  {i + 1} {CORNER_LABELS[i]:<2} : ({x}, {y})")
    print(f"Polygon area     : {area:.1f} px^2")
    print(f"Output image     : {OUTPUT_IMAGE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
