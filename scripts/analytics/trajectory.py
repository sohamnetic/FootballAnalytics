import pandas as pd


class TrajectoryEngine:

    def __init__(self, csv_path):

        self.df = pd.read_csv(csv_path)

    def get_player_trajectory(self, stable_id):

        player = self.df[self.df["track_id"] == stable_id]

        return list(
            zip(
                player["center_x"],
                player["center_y"]
            )
        )