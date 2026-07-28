import csv
from pathlib import Path


class CoordinateLogger:

    def __init__(self, output_file):

        self.output_file = Path(output_file)

        self.output_file.parent.mkdir(parents=True, exist_ok=True)

        self.file = open(self.output_file, "w", newline="")

        self.writer = csv.writer(self.file)

        self.writer.writerow([
            "frame",
            "track_id",
            "class",
            "confidence",
            "x1",
            "y1",
            "x2",
            "y2",
            "center_x",
            "center_y"
        ])

    def log(
        self,
        frame_number,
        track_id,
        cls_name,
        confidence,
        x1,
        y1,
        x2,
        y2
    ):

        center_x = int((x1 + x2) / 2)
        center_y = int(y2)

        self.writer.writerow([
            frame_number,
            track_id,
            cls_name,
            confidence,
            x1,
            y1,
            x2,
            y2,
            center_x,
            center_y
        ])

    def close(self):
        self.file.close()