"""
Camera motion for a panning/zooming match camera.

Chains frame-to-frame similarity transforms, estimated from background
optical flow with people masked out, into one transform per frame that maps
that frame's pixels onto the first frame's pixels. Positions mapped this way
stay comparable across a pan; raw pixels do not.
"""
import cv2
import numpy as np


class CameraMotion:

    def __init__(self, scale=0.5):
        self.scale = scale
        self._prev_gray = None
        self._prev_mask = None
        self._cum = np.eye(3)
        s = np.diag([scale, scale, 1.0])
        self._to_small, self._to_full = s, np.linalg.inv(s)
        self._lk = dict(
            winSize=(21, 21), maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
        )

    def update(self, frame, boxes):
        gray = cv2.cvtColor(
            cv2.resize(frame, None, fx=self.scale, fy=self.scale), cv2.COLOR_BGR2GRAY
        )
        mask = np.full(gray.shape, 255, np.uint8)
        for x1, y1, x2, y2 in (np.asarray(boxes, float).reshape(-1, 4) * self.scale).astype(int):
            cv2.rectangle(mask, (x1 - 4, y1 - 4), (x2 + 4, y2 + 4), 0, -1)

        if self._prev_gray is not None:
            p0 = cv2.goodFeaturesToTrack(self._prev_gray, 400, 0.01, 8, mask=self._prev_mask)
            if p0 is not None and len(p0) >= 12:
                p1, status, _ = cv2.calcOpticalFlowPyrLK(self._prev_gray, gray, p0, None, **self._lk)
                good = status.reshape(-1) == 1
                if good.sum() >= 12:
                    # current -> previous, in small-image pixels
                    a, _ = cv2.estimateAffinePartial2D(
                        p1[good], p0[good], method=cv2.RANSAC, ransacReprojThreshold=2.0
                    )
                    if a is not None:
                        step = self._to_full @ np.vstack([a, [0, 0, 1]]) @ self._to_small
                        self._cum = self._cum @ step

        self._prev_gray, self._prev_mask = gray, mask
        return self._cum.copy()


def summarize_motion(transforms, width, height):
    """How much the view moved over the clip: pan range of the image centre
    (in first-frame pixels) and zoom range. Used to decide whether pixel-space
    geometry such as fixed goal boxes can be trusted."""
    if not transforms:
        return {"moving": False, "pan_x_px": 0.0, "pan_y_px": 0.0, "zoom_ratio": 1.0}
    centre = np.array([width / 2, height / 2, 1.0])
    pts = np.array([t @ centre for t in transforms])[:, :2]
    scales = np.array([np.sqrt(abs(np.linalg.det(t[:2, :2]))) for t in transforms])
    pan_x = float(pts[:, 0].max() - pts[:, 0].min())
    pan_y = float(pts[:, 1].max() - pts[:, 1].min())
    zoom = float(scales.max() / max(scales.min(), 1e-6))
    moving = pan_x > 0.15 * width or pan_y > 0.15 * height or zoom > 1.15
    return {"moving": bool(moving), "pan_x_px": round(pan_x, 1), "pan_y_px": round(pan_y, 1), "zoom_ratio": round(zoom, 3)}
