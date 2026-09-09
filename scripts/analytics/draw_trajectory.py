import cv2
import pandas as pd
from pathlib import Path


class TrajectoryDrawer:

    def __init__(self, csv_path, video_path):

        self.df = pd.read_csv(csv_path)

        self.video_path = video_path

    def draw(self, player_id):

        cap = cv2.VideoCapture(str(self.video_path))

        ret, frame = cap.read()

        cap.release()

        if not ret:
            print("Cannot open video")
            return

        player = self.df[self.df["track_id"] == player_id]

        points = list(zip(player["center_x"], player["center_y"]))

        # Draw trajectory
        for i in range(1, len(points)):

            cv2.line(
                frame,
                points[i - 1],
                points[i],
                (0, 255, 255),
                2
            )

        # Draw points
        for p in points:

            cv2.circle(
                frame,
                p,
                2,
                (0, 0, 255),
                -1
            )

        cv2.imshow(f"Trajectory - Player {player_id}", frame)

        cv2.waitKey(0)

        cv2.destroyAllWindows()