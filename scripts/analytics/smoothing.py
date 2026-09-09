import pandas as pd


class TrajectorySmoother:

    def __init__(self, csv_path):

        self.df = pd.read_csv(csv_path)

    def smooth(self, player_id, window=5):

        player = self.df[self.df["track_id"] == player_id].copy()

        player["smooth_x"] = (
            player["center_x"]
            .rolling(window=window, center=True)
            .mean()
        )

        player["smooth_y"] = (
            player["center_y"]
            .rolling(window=window, center=True)
            .mean()
        )

        player = player.fillna(method="bfill")
        player = player.fillna(method="ffill")

        return player