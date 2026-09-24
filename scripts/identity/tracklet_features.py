"""
Collects what the identity resolver needs while tracking runs (so we don't
read the video twice): turf under each person, kit colour, ReID embeddings,
shirt number OCR, and the camera motion per frame.
"""
import re
import time
from collections import defaultdict

import cv2
import numpy as np

from config.config import (
    IDENTITY_KIT_MIN_SAT,
    IDENTITY_OCR_ENABLED,
    IDENTITY_OCR_EVERY,
    IDENTITY_OCR_MAX_PER_TRACK,
    IDENTITY_OCR_MIN_CONF,
    IDENTITY_OCR_MIN_HEIGHT_PX,
    IDENTITY_PLAYER_TURF_MIN_STRONG_KIT,
    IDENTITY_REID_EVERY,
    IDENTITY_REID_WEIGHTS,
    DEVICE,
)
from scripts.identity.resolver import normalize_number, rank_number_votes
from scripts.vision.turf import turf_mask

KIT_HUE_BINS = 18
# crops overlapping someone else this much are skipped for ReID
_CLEAN_OVERLAP_MAX = 0.15
_CLEAN_MIN_HEIGHT_PX = 60
_DIGITS = re.compile(r"^\d{1,2}$")


class TrackletFeatureCollector:

    def __init__(self):
        from boxmot.reid.core.runtime import ReID

        device = f"cuda:{DEVICE}" if isinstance(DEVICE, int) else DEVICE
        self._reid = ReID(weights=IDENTITY_REID_WEIGHTS, device=device)
        self._ocr = None
        if IDENTITY_OCR_ENABLED:
            import easyocr

            self._ocr = easyocr.Reader(["en"], gpu=isinstance(DEVICE, int), verbose=False)

        self._ocr_eligible = defaultdict(int)
        self._ocr_count = defaultdict(int)
        self._ocr_votes = defaultdict(lambda: defaultdict(float))
        self._ocr_settled = set()
        self.timing = defaultdict(float)
        self.ocr_calls = 0

        self.rows = []          # frame, track_id, conf, x1, y1, x2, y2
        self.turf = []
        self.kit_hist = []
        self.kit_sat = []
        # sum of ReID vectors per track (storing one per detection ran out of
        # memory on a full match). clean = not blocked by someone else
        self._emb_sum = {}
        self._emb_n = defaultdict(int)
        self._emb_clean_sum = {}
        self._emb_clean_n = defaultdict(int)
        self.ocr_reads = []     # track_id, frame, text, conf
        self.camera = {}

    def add_frame(self, frame_number, frame, detections, camera_transform):
        boxes = [d["bbox"] for d in detections]
        self.camera[frame_number] = camera_transform
        if not detections:
            return

        h_img, w_img = frame.shape[:2]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        reid_rows, reid_boxes = [], []
        clean = self._unoccluded(boxes)

        for i, det in enumerate(detections):
            tid = det["track_id"]
            x1, y1, x2, y2 = det["bbox"]
            row = len(self.rows)
            self.rows.append((frame_number, tid, det["confidence"], x1, y1, x2, y2))

            turf, hist, sat = self._colour_evidence(hsv, x1, y1, x2, y2, w_img, h_img)
            self.turf.append(turf)
            self.kit_hist.append(hist)
            self.kit_sat.append(sat)

            height = y2 - y1
            if frame_number % IDENTITY_REID_EVERY == 0 and height >= 40:
                reid_rows.append((tid, clean[i] and height >= _CLEAN_MIN_HEIGHT_PX))
                reid_boxes.append((x1, y1, x2, y2))

            if (
                self._ocr is not None
                and tid not in self._ocr_settled
                and height >= IDENTITY_OCR_MIN_HEIGHT_PX
                and sat >= IDENTITY_KIT_MIN_SAT
                and turf >= IDENTITY_PLAYER_TURF_MIN_STRONG_KIT
            ):
                k = self._ocr_eligible[tid]
                self._ocr_eligible[tid] = k + 1
                if k % IDENTITY_OCR_EVERY == 0 and self._ocr_count[tid] < IDENTITY_OCR_MAX_PER_TRACK:
                    self._ocr_count[tid] += 1
                    self._read_number(frame, tid, frame_number, x1, y1, x2, y2)

        if reid_rows:
            t0 = time.perf_counter()
            feats = np.asarray(
                self._reid(frame, boxes=np.asarray(reid_boxes, np.float32)), np.float32
            )
            feats /= np.maximum(np.linalg.norm(feats, axis=1, keepdims=True), 1e-9)
            for (tid, is_clean), vec in zip(reid_rows, feats):
                self._emb_sum[tid] = self._emb_sum.get(tid, 0) + vec
                self._emb_n[tid] += 1
                if is_clean:
                    self._emb_clean_sum[tid] = self._emb_clean_sum.get(tid, 0) + vec
                    self._emb_clean_n[tid] += 1
            self.timing["reid_s"] += time.perf_counter() - t0

    @staticmethod
    def _unoccluded(boxes):
        if len(boxes) < 2:
            return [True] * len(boxes)
        b = np.asarray(boxes, float)
        ix = np.clip(np.minimum(b[:, None, 2], b[None, :, 2]) - np.maximum(b[:, None, 0], b[None, :, 0]), 0, None)
        iy = np.clip(np.minimum(b[:, None, 3], b[None, :, 3]) - np.maximum(b[:, None, 1], b[None, :, 1]), 0, None)
        area = np.maximum((b[:, 2] - b[:, 0]) * (b[:, 3] - b[:, 1]), 1.0)
        frac = ix * iy / area[:, None]
        np.fill_diagonal(frac, 0)
        return list(frac.max(1) < _CLEAN_OVERLAP_MAX)

    @staticmethod
    def _colour_evidence(hsv, x1, y1, x2, y2, w_img, h_img):
        x1c, x2c, y1c, y2c = max(0, x1), min(w_img, x2), max(0, y1), min(h_img, y2)
        w, h = x2c - x1c, y2c - y1c
        hist = np.zeros(KIT_HUE_BINS, np.float32)
        if w <= 2 or h <= 4:
            return 0.0, hist, 0.0

        # is there turf around the feet?
        gx1, gx2 = max(0, int(x1 - 0.2 * w)), min(w_img, int(x2 + 0.2 * w))
        band = hsv[max(0, y2 - 4):min(h_img, y2 + 10), gx1:gx2].reshape(-1, 3)
        turf = float(turf_mask(band).mean()) if len(band) else 0.0

        # shirt colour (skip turf pixels)
        torso = hsv[
            y1c + int(0.15 * h): y1c + int(0.50 * h),
            x1c + int(0.2 * w): x2c - int(0.2 * w),
        ].reshape(-1, 3)
        torso = torso[~turf_mask(torso)] if len(torso) else torso
        sat = 0.0
        if len(torso):
            saturated = torso[:, 1] >= 70
            sat = float(saturated.mean())
            hues = torso[saturated, 0]
            if len(hues):
                counts, _ = np.histogram(hues, bins=KIT_HUE_BINS, range=(0, 180))
                hist = (counts / counts.sum()).astype(np.float32)
        return turf, hist, sat

    def _read_number(self, frame, tid, frame_number, x1, y1, x2, y2):
        crop = frame[max(0, y1):y2, max(0, x1):x2]
        if crop.size == 0:
            return
        t0 = time.perf_counter()
        up = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        for _, text, conf in self._ocr.readtext(up, allowlist="0123456789", detail=1):
            if _DIGITS.match(text):
                self.ocr_reads.append((tid, frame_number, text, float(conf)))
                if conf >= IDENTITY_OCR_MIN_CONF:
                    self._ocr_votes[tid][normalize_number(text)] += float(conf)
        self.ocr_calls += 1
        self.timing["ocr_s"] += time.perf_counter() - t0
        # stop once we're sure of the number
        _, support, rival = rank_number_votes(self._ocr_votes[tid])
        if support >= 8.0 and support >= 3.0 * rival:
            self._ocr_settled.add(tid)

    def as_arrays(self):
        rows = np.asarray(self.rows, dtype=np.float64).reshape(-1, 7)
        track_emb = {}
        for tid, total in self._emb_sum.items():
            # use the clean crops if there are enough
            vec = self._emb_clean_sum[tid] if self._emb_clean_n[tid] >= 3 else total
            track_emb[tid] = vec / max(float(np.linalg.norm(vec)), 1e-9)
        return {
            "rows": rows,
            "turf": np.asarray(self.turf, np.float32),
            "kit_hist": np.asarray(self.kit_hist, np.float32).reshape(-1, KIT_HUE_BINS),
            "kit_sat": np.asarray(self.kit_sat, np.float32),
            "track_emb": track_emb,
            "ocr_reads": list(self.ocr_reads),
            "camera": dict(self.camera),
        }
