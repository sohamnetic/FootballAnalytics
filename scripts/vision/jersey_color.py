import cv2
import numpy as np


class JerseyColorExtractor:
    """
    Extracts the dominant jersey colour from a player's bounding box.
    """

    def __init__(self, upper_body_ratio=0.40):
        self.upper_body_ratio = upper_body_ratio

    def extract_color(self, frame, bbox):
        """
        Parameters
        ----------
        frame : np.ndarray
            Original video frame

        bbox : tuple
            (x1, y1, x2, y2)

        Returns
        -------
        tuple
            Average BGR colour
        """

        x1, y1, x2, y2 = bbox

        # Keep inside image
        h, w = frame.shape[:2]

        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(w, x2)
        y2 = min(h, y2)

        if x2 <= x1 or y2 <= y1:
            return None

        player_crop = frame[y1:y2, x1:x2]

        if player_crop.size == 0:
            return None

        crop_height = player_crop.shape[0]

        upper_crop = player_crop[
            0:int(crop_height * self.upper_body_ratio),
            :
        ]

        if upper_crop.size == 0:
            return None

        average_color = np.mean(
            upper_crop,
            axis=(0, 1)
        )

        b, g, r = average_color

        return (
            int(b),
            int(g),
            int(r)
        )