import math
import pandas as pd


class MotionEngine:
    """
    Pixel-space motion stats from a coordinate CSV.

    identity_column:
        Column used to group a player. Default is "track_id" so existing
        tests keep working. The MVP pipeline passes "stable_id" when that
        column has values.

    Same-frame duplicates:
        IdentityManager can assign the same stable_id to two ByteTrack IDs
        in one frame (old ID still present after a rematch). Those rows are
        reduced to the highest-confidence detection per frame, then sorted
        by frame so trajectory / distance / speed stay chronological.
    """

    def __init__(self, csv_path, fps, identity_column="track_id"):

        self.df = pd.read_csv(csv_path)
        self.fps = fps
        self.identity_column = identity_column

        if identity_column not in self.df.columns:
            raise ValueError(
                f"MotionEngine identity_column {identity_column!r} "
                f"not in CSV columns: {list(self.df.columns)}"
            )

    def _player_rows(self, player_id):

        player = self.df[self.df[self.identity_column] == player_id].copy()

        if player.empty:
            return player

        if "frame" in player.columns:
            sort_cols = ["frame"]
            ascending = [True]
            if "confidence" in player.columns:
                sort_cols.append("confidence")
                ascending.append(False)
            player = player.sort_values(sort_cols, ascending=ascending)
            player = player.drop_duplicates(subset=["frame"], keep="first")
            player = player.sort_values("frame")
        else:
            player = player.sort_values(
                list(player.columns[:1])
            )

        return player

    # --------------------------
    # Raw Trajectory
    # --------------------------

    def get_trajectory(self, player_id):

        player = self._player_rows(player_id)

        return list(
            zip(
                player["center_x"],
                player["center_y"]
            )
        )

    # --------------------------
    # Smoothed Trajectory
    # --------------------------

    def get_smoothed_trajectory(self, player_id, window=5):

        player = self._player_rows(player_id)

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

        player = player.bfill().ffill()

        return list(
            zip(
                player["smooth_x"],
                player["smooth_y"]
            )
        )

    # --------------------------
    # Distance
    # --------------------------

    def get_distance(self, player_id):

        points = self.get_smoothed_trajectory(player_id)

        distance = 0

        for i in range(1, len(points)):

            distance += math.dist(
                points[i - 1],
                points[i]
            )

        return distance

    # --------------------------
    # Speed
    # --------------------------

    def get_speed(self, player_id):

        points = self.get_smoothed_trajectory(player_id)

        dt = 1 / self.fps

        speeds = []

        for i in range(1, len(points)):

            d = math.dist(
                points[i - 1],
                points[i]
            )

            speeds.append(d / dt)

        return speeds

    def get_all_players(self):

        values = self.df[self.identity_column].dropna()
        values = values[values.astype(str).str.strip() != ""]

        players = sorted(values.unique().tolist())

        return players
