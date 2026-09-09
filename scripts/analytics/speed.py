import math
import pandas as pd


class SpeedEngine:

    def __init__(self, csv_path, fps):

        self.df = pd.read_csv(csv_path)
        self.fps = fps

    def calculate_speed(self, player_id):

        player = self.df[self.df["track_id"] == player_id]

        points = list(
            zip(
                player["center_x"],
                player["center_y"]
            )
        )

        if len(points) < 2:
            return []

        speeds = []

        dt = 1 / self.fps

        for i in range(1, len(points)):

            distance = math.dist(
                points[i - 1],
                points[i]
            )

            speed = distance / dt

            speeds.append(speed)

        return speeds