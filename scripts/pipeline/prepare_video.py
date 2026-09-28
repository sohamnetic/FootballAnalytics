"""
Convert high frame rate uploads (e.g. 60 fps) to 30 fps before analysis.

Everything was tuned and checked on 30 fps video, and analysing every frame
of a 60 fps video takes twice as long for no real gain. The converted copy
is H.264, which OpenCV also decodes much faster than AV1.

Only the part being analysed (start_time / duration) is converted, so the
copy starts at 0.
"""
import json
import shutil
import subprocess
from pathlib import Path

import cv2

from config.config import ANALYSIS_FPS, FFMPEG_BIN


def _ffmpeg():
    return FFMPEG_BIN or shutil.which("ffmpeg")


def needs_resample(video_path):
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 0
    cap.release()
    return ANALYSIS_FPS > 0 and fps > ANALYSIS_FPS * 1.2, fps


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True).returncode == 0


def prepare_video(video_path, out_path, start_time=0, duration=None):
    """
    Returns (video to analyse, start_time, duration). If no conversion is
    needed (or ffmpeg is missing) the original video and times come back.
    """
    video_path, out_path = Path(video_path), Path(out_path)
    resample, fps = needs_resample(video_path)
    ffmpeg = _ffmpeg()
    if not resample:
        return video_path, start_time, duration
    if not ffmpeg:
        print(f"ffmpeg not found, analysing all {fps:.0f} fps (slower)")
        return video_path, start_time, duration

    # reuse the copy if it was made from the same file and window
    stat = video_path.stat()
    key = {"source": str(video_path), "size": stat.st_size, "mtime": stat.st_mtime,
           "start": start_time or 0, "duration": duration, "fps": ANALYSIS_FPS}
    info = out_path.with_suffix(".json")
    if out_path.exists() and info.exists() and json.loads(info.read_text()) == key:
        print(f"Converting video to {ANALYSIS_FPS} fps: reusing {out_path}")
        return out_path, 0, None

    print(f"Converting video to {ANALYSIS_FPS} fps (source is {fps:.2f} fps)...")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    window = []
    if start_time:
        window += ["-ss", str(start_time)]
    if duration:
        window += ["-t", str(duration)]
    common = ["-an", "-vf", f"fps={ANALYSIS_FPS}", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    # GPU decode + encode if possible, otherwise plain CPU
    attempts = [
        [ffmpeg, "-v", "error", "-y", "-hwaccel", "cuda", *window, "-i", str(video_path), *common,
         "-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "19", "-b:v", "0", str(out_path)],
        [ffmpeg, "-v", "error", "-y", *window, "-i", str(video_path), *common,
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(out_path)],
    ]
    for cmd in attempts:
        if _run(cmd) and out_path.exists() and out_path.stat().st_size > 0:
            info.write_text(json.dumps(key))
            print(f"Converted video: {out_path}")
            return out_path, 0, None
    print("Couldn't convert the video, analysing the original (slower)")
    out_path.unlink(missing_ok=True)
    return video_path, start_time, duration
