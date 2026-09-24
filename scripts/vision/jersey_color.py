import cv2
import numpy as np


class JerseyColorExtractor:
    """Gets the shirt colour of a player."""

    def __init__(self, upper_body_ratio=0.40):
        self.upper_body_ratio = upper_body_ratio

    def extract_color(self, frame, bbox):
        """Average BGR colour of the shirt area in bbox (x1, y1, x2, y2)."""

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

    @staticmethod
    def bgr_to_hsv(bgr):
        """Convert a BGR tuple to OpenCV HSV (H 0-180, S/V 0-255)."""
        pixel = np.uint8([[list(bgr)]])
        hsv = cv2.cvtColor(pixel, cv2.COLOR_BGR2HSV)[0, 0]
        return (int(hsv[0]), int(hsv[1]), int(hsv[2]))

    @staticmethod
    def bgr_to_lab(bgr):
        """BGR -> OpenCV Lab."""
        pixel = np.uint8([[list(bgr)]])
        lab = cv2.cvtColor(pixel, cv2.COLOR_BGR2LAB)[0, 0]
        return (int(lab[0]), int(lab[1]), int(lab[2]))

    # Colour histograms of shirt and shorts. Works a lot better than one
    # average colour, which shadows and grass mess up.

    def extract_descriptor(self, frame, bbox, bins=12):
        """Returns (shirt_hist, shorts_hist). Either can be None, or None if both fail."""
        x1, y1, x2, y2 = bbox
        h, w = frame.shape[:2]

        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(w, x2)
        y2 = min(h, y2)

        if x2 <= x1 or y2 <= y1:
            return None

        crop = frame[y1:y2, x1:x2]
        crop_height = crop.shape[0]
        if crop_height < 4:
            return None

        upper = crop[int(crop_height * 0.08):int(crop_height * 0.40), :]
        lower = crop[int(crop_height * 0.55):int(crop_height * 0.90), :]

        upper_hist = self._region_histogram(upper, bins)
        lower_hist = self._region_histogram(lower, bins)

        if upper_hist is None and lower_hist is None:
            return None

        return (upper_hist, lower_hist)

    @staticmethod
    def _region_histogram(region, bins):
        if region.size == 0:
            return None
        hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [bins, bins], [0, 180, 0, 256])
        cv2.normalize(hist, hist, alpha=1.0, norm_type=cv2.NORM_L1)
        return hist

    @staticmethod
    def descriptor_distance(a, b):
        """0 = same colours, 1 = totally different. None if we can't compare."""
        if a is None or b is None:
            return None
        dists = []
        for region_a, region_b in zip(a, b):
            if region_a is None or region_b is None:
                continue
            dists.append(cv2.compareHist(region_a, region_b, cv2.HISTCMP_BHATTACHARYYA))
        if not dists:
            return None
        return sum(dists) / len(dists)

    @staticmethod
    def descriptor_running_avg(old, new):
        """Average of two descriptors."""
        if old is None:
            return new
        if new is None:
            return old
        return tuple(
            (ro + rn) / 2.0 if (ro is not None and rn is not None) else (rn if ro is None else ro)
            for ro, rn in zip(old, new)
        )