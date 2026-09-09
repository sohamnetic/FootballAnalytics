import math
import pandas as pd


class DistanceEngine:

    def __init__(self, csv_path):

        self.df = pd.read_csv(csv_path)

    def calculate_distance(self, player_id):

        player = self.df[self.df["track_id"] == player_id]

        points = list(
            zip(
                player["center_x"],
                player["center_y"]
            )
        )

        if len(points) < 2:
            return 0

        total_distance = 0

        for i in range(1, len(points)):

            total_distance += math.dist(
                points[i - 1],
                points[i]
            )

        return total_distance