"""Is this pixel turf? (HSV range is in config.py)"""
from config.config import IDENTITY_TURF_HSV_MAX, IDENTITY_TURF_HSV_MIN


def turf_mask(hsv_pixels):
    """hsv_pixels is an (N, 3) array in OpenCV HSV."""
    lo, hi = IDENTITY_TURF_HSV_MIN, IDENTITY_TURF_HSV_MAX
    return (
        (hsv_pixels[:, 0] >= lo[0]) & (hsv_pixels[:, 0] <= hi[0])
        & (hsv_pixels[:, 1] >= lo[1]) & (hsv_pixels[:, 1] <= hi[1])
        & (hsv_pixels[:, 2] >= lo[2]) & (hsv_pixels[:, 2] <= hi[2])
    )
