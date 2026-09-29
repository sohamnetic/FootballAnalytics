"""
Quick "is this football?" check before the expensive analysis.

Looks at about 20 frames spread over the part being analysed. A frame counts
as football when enough of it is green turf and several people are on it.
Replays, close-ups and crowd shots are fine as long as a fair share of the
frames look like play. Takes a few seconds; a movie clip or a random video
gets stopped here instead of burning an hour of GPU.
"""
import shutil
import subprocess

import cv2
import numpy as np

from config.config import DEVICE, FFMPEG_BIN, PERSON_MODEL
from scripts.vision.turf import turf_mask

SAMPLES = 20
MIN_TURF = 0.20        # share of the frame that is pitch-green
MIN_PEOPLE_ON_TURF = 3
MIN_PLAY_SHARE = 0.35  # share of sampled frames that must look like play

NOT_FOOTBALL = ("This doesn't look like a football match. Upload match footage filmed "
                "from the side of the pitch, with the green playing surface in view.")
UNREADABLE = "We couldn't read frames from this video. Try exporting it again as MP4 (H.264)."


def _ffmpeg_frame(ffmpeg, video_path, t):
    """One frame at t seconds. ffmpeg seeks by keyframe, which is far
    faster than OpenCV on AV1 (seconds instead of a minute for 20 frames)."""
    run = subprocess.run(
        [ffmpeg, "-v", "error", "-ss", f"{t:.3f}", "-i", str(video_path), "-frames:v", "1",
         "-f", "image2pipe", "-vcodec", "png", "-"],
        capture_output=True,
    )
    if run.returncode != 0 or not run.stdout:
        return None
    return cv2.imdecode(np.frombuffer(run.stdout, np.uint8), cv2.IMREAD_COLOR)


def _sample_frames(video_path, start_time, duration):
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    first = int(round((start_time or 0) * fps))
    last = total - 1 if not duration else min(total - 1, first + int(duration * fps))
    frames = []
    if total <= 0 or last <= first:
        cap.release()
        return frames
    positions = np.linspace(first, last, SAMPLES).astype(int)
    ffmpeg = FFMPEG_BIN or shutil.which("ffmpeg")
    if ffmpeg:
        cap.release()
        for idx in positions:
            frame = _ffmpeg_frame(ffmpeg, video_path, idx / fps)
            if frame is not None:
                frames.append(frame)
        if len(frames) >= 3:
            return frames
        frames = []
        cap = cv2.VideoCapture(str(video_path))
    for idx in positions:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, frame = cap.read()
        if ok:
            frames.append(frame)
    cap.release()
    return frames


def _on_turf(hsv, boxes):
    """People whose feet are on turf-coloured ground."""
    h, w = hsv.shape[:2]
    count = 0
    for x1, y1, x2, y2 in boxes:
        fx, fy = int((x1 + x2) / 2), int(min(y2 + 0.05 * (y2 - y1), h - 1))
        patch = hsv[max(0, fy - 4):fy + 5, max(0, fx - 8):min(w, fx + 9)].reshape(-1, 3)
        if len(patch) and turf_mask(patch).mean() > 0.3:
            count += 1
    return count


def check_footage(video_path, start_time=0, duration=None, model=None):
    """Returns (ok, message, details)."""
    frames = _sample_frames(video_path, start_time, duration)
    if len(frames) < 3:
        return False, UNREADABLE, {"frames": len(frames)}

    if model is None:
        from ultralytics import YOLO
        model = YOLO(PERSON_MODEL)
    small = [cv2.resize(f, (960, int(f.shape[0] * 960 / f.shape[1]))) for f in frames]
    results = model.predict(small, classes=[0], conf=0.3, imgsz=960, device=DEVICE, verbose=False)

    play = []
    for frame, result in zip(small, results):
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        turf = float(turf_mask(hsv.reshape(-1, 3)).mean())
        people = _on_turf(hsv, result.boxes.xyxy.cpu().numpy()) if result.boxes is not None else 0
        play.append(turf >= MIN_TURF and people >= MIN_PEOPLE_ON_TURF)
    share = float(np.mean(play))
    details = {"frames": len(frames), "play_share": round(share, 2)}
    return share >= MIN_PLAY_SHARE, NOT_FOOTBALL, details
