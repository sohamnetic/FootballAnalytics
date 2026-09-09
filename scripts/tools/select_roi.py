import cv2
import json
import numpy as np

from config.config import TEST_VIDEO, PROJECT_ROOT

# =====================================================
# Paths
# =====================================================

ROI_FOLDER = PROJECT_ROOT / "data" / "roi"
ROI_FOLDER.mkdir(parents=True, exist_ok=True)

ROI_FILE = ROI_FOLDER / "camera_001.json"

# =====================================================
# Globals
# =====================================================

points = []
frame = None

# =====================================================
# Mouse Callback
# =====================================================

def mouse_callback(event, x, y, flags, param):

    global points

    # -------------------------
    # Left Click
    # -------------------------
    if event == cv2.EVENT_LBUTTONDOWN:

        if len(points) < 4:

            points.append([x, y])

            print(f"Corner {len(points)} : ({x}, {y})")

    # -------------------------
    # Right Click
    # -------------------------
    elif event == cv2.EVENT_RBUTTONDOWN:

        if len(points):

            removed = points.pop()

            print(f"Removed : {removed}")

# =====================================================
# Draw
# =====================================================

def draw():

    canvas = frame.copy()

    # Draw polygon only after 2 points
    if len(points) >= 2:

        pts = np.array(points, np.int32)

        closed = len(points) == 4

        cv2.polylines(
            canvas,
            [pts],
            closed,
            (0,255,0),
            2
        )

    # Draw points
    for i, p in enumerate(points):

        cv2.circle(
            canvas,
            tuple(p),
            7,
            (0,0,255),
            -1
        )

        cv2.putText(
            canvas,
            str(i+1),
            (p[0]+12,p[1]-12),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255,255,255),
            2
        )

    instructions = [

        "Select ONLY 4 pitch corners",

        "1 Top Left",

        "2 Top Right",

        "3 Bottom Right",

        "4 Bottom Left",

        "",

        "Left Click : Add",

        "Right Click : Undo",

        "R : Reset",

        "S : Save",

        "Q : Quit"
    ]

    y = 30

    for text in instructions:

        cv2.putText(

            canvas,

            text,

            (20,y),

            cv2.FONT_HERSHEY_SIMPLEX,

            0.65,

            (255,255,255),

            2

        )

        y += 28

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

        print("Cannot read video.")

        return

    print("="*60)
    print("Select the FOUR OUTER corners of the football pitch")
    print()
    print("Order:")
    print("1 -> Top Left")
    print("2 -> Top Right")
    print("3 -> Bottom Right")
    print("4 -> Bottom Left")
    print("="*60)

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

            print("Reset.")

        elif key == ord("s"):

            if len(points) != 4:

                print("Please select EXACTLY 4 corners.")

                continue

            roi = {

                "camera_name":"camera_001",

                "video_resolution":[
                    frame.shape[1],
                    frame.shape[0]
                ],

                "corners":points

            }

            with open(ROI_FILE,"w") as f:

                json.dump(
                    roi,
                    f,
                    indent=4
                )

            print("\nROI Saved Successfully!")

            print(ROI_FILE)

            break

    cv2.destroyAllWindows()

if __name__ == "__main__":

    main()