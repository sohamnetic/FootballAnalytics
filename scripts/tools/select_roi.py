import cv2
import json
import numpy as np

from pathlib import Path
from config.config import TEST_VIDEO, PROJECT_ROOT

# =====================================================
# Configuration
# =====================================================

ROI_FOLDER = PROJECT_ROOT / "data" / "roi"
ROI_FOLDER.mkdir(parents=True, exist_ok=True)

ROI_FILE = ROI_FOLDER / "camera_001.json"

# =====================================================
# Global Variables
# =====================================================

points = []

frame = None
display = None


# =====================================================
# Mouse Callback
# =====================================================

def mouse_callback(event, x, y, flags, param):
    global points

    # Left Click -> Add Point
    if event == cv2.EVENT_LBUTTONDOWN:
        points.append([x, y])

    # Right Click -> Remove Last Point
    elif event == cv2.EVENT_RBUTTONDOWN:
        if len(points) > 0:
            points.pop()


# =====================================================
# Draw Everything
# =====================================================

def draw():

    canvas = frame.copy()

    # Draw filled polygon
    if len(points) >= 3:

        overlay = canvas.copy()

        pts = np.array(points, dtype=np.int32)

        cv2.fillPoly(
            overlay,
            [pts],
            (255, 0, 0)
        )

        alpha = 0.25

        canvas = cv2.addWeighted(
            overlay,
            alpha,
            canvas,
            1 - alpha,
            0
        )

    # Draw polygon lines
    if len(points) >= 2:

        pts = np.array(points, dtype=np.int32)

        cv2.polylines(
            canvas,
            [pts],
            False,
            (0, 255, 0),
            2
        )

    # Draw Points + Numbers
    for i, p in enumerate(points):

        cv2.circle(
            canvas,
            tuple(p),
            6,
            (0, 0, 255),
            -1
        )

        cv2.putText(
            canvas,
            str(i + 1),
            (p[0] + 10, p[1] - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            2
        )

    instructions = [
        "Left Click : Add Point",
        "Right Click : Undo",
        "S : Save",
        "R : Reset",
        "Q : Quit"
    ]

    y = 30

    for text in instructions:

        cv2.putText(
            canvas,
            text,
            (20, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255,255,255),
            2
        )

        y += 30

    return canvas


# =====================================================
# Main
# =====================================================

def main():

    global frame

    cap = cv2.VideoCapture(str(TEST_VIDEO))

    ret, frame = cap.read()

    cap.release()

    if not ret:
        print("Unable to open video.")
        return

    cv2.namedWindow("ROI Selector")

    cv2.setMouseCallback(
        "ROI Selector",
        mouse_callback
    )

    while True:

        canvas = draw()

        cv2.imshow(
            "ROI Selector",
            canvas
        )

        key = cv2.waitKey(20) & 0xFF

        if key == ord("q"):
            break

        elif key == ord("r"):
            points.clear()

        elif key == ord("s"):

            if len(points) < 3:
                print("Select at least 3 points.")
                continue

            roi_data = {
                "camera_name": "camera_001",
                "video_resolution": [
                    frame.shape[1],
                    frame.shape[0]
                ],
                "polygon": points
            }

            with open(ROI_FILE, "w") as f:
                json.dump(
                    roi_data,
                    f,
                    indent=4
                )

            print("\nROI Saved Successfully!")
            print(ROI_FILE)

            break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()