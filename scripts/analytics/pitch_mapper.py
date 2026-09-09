import cv2
import pandas as pd


class PitchMapper:

    def __init__(self, csv_path, pitch_path):

        self.df = pd.read_csv(csv_path)

        self.pitch = cv2.imread(str(pitch_path))
        self.pitch = cv2.rotate(
    self.pitch,
    cv2.ROTATE_90_CLOCKWISE
)

        self.pitch_h, self.pitch_w = self.pitch.shape[:2]

    def map_player(self, player_id):

        player = self.df[self.df["track_id"] == player_id]

        mapped = []

        for _, row in player.iterrows():

            x = row["center_x"] / 1920
            y = row["center_y"] / 1080

            px = int(x * self.pitch_w)
            py = int(y * self.pitch_h)

            mapped.append((px, py))

        return mapped

    def draw(self, player_id):

        image = self.pitch.copy()

        points = self.map_player(player_id)

        for i in range(1, len(points)):

            cv2.line(
                image,
                points[i - 1],
                points[i],
                (0, 0, 255),
                2
            )

        return image