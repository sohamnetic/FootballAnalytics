import cv2
import numpy as np


class HeatmapEngine:

    def __init__(self, frame_shape):

        self.height = frame_shape[0]
        self.width = frame_shape[1]

    def generate(self, trajectory):

        heat = np.zeros(
            (self.height, self.width),
            dtype=np.float32
        )

        for x, y in trajectory:

            x = int(x)
            y = int(y)

            if 0 <= x < self.width and 0 <= y < self.height:

                cv2.circle(
                    heat,
                    (x, y),
                    25,
                    1,
                    -1
                )

        heat = cv2.GaussianBlur(
            heat,
            (51, 51),
            0
        )

        heat = cv2.normalize(
            heat,
            None,
            0,
            255,
            cv2.NORM_MINMAX
        )

        heat = heat.astype(np.uint8)

        heat = cv2.applyColorMap(
            heat,
            cv2.COLORMAP_JET
        )

        return heat