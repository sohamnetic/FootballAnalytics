from ultralytics import YOLO
from pathlib import Path
import os
import time

import cv2

from config.config import (
    YOLO_MODEL,
    TEST_VIDEO,
    TRACKER_CONFIG,
    TRACKING_OUTPUT,
    PROJECT_ROOT,
    DEVICE,
    DEVICE_LABEL,
    BALL_CLASS_ID,
    BALL_CLASS_NAME,
    BALL_CONFIDENCE,
    BALL_IMGSZ,
)

from scripts.coordinate_logger import CoordinateLogger
from scripts.identity.identity_manager import IdentityManager

# Optional short run: set MAX_FRAMES (e.g. 90) then unset it for a full match.
MAX_FRAMES = int(os.environ["MAX_FRAMES"]) if os.environ.get("MAX_FRAMES") else None

# Default CSV path used by standalone `python -m scripts.track`
COORDINATE_OUTPUT = (
    PROJECT_ROOT /
    "outputs" /
    "coordinates" /
    "match_test.csv"
)


def _video_fps(video_path: Path) -> float:
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    if fps is None or fps <= 0:
        raise RuntimeError(f"Cannot read FPS from {video_path}")
    return float(fps)


def run_tracking(
    video_path=None,
    coordinate_output=None,
    max_frames=None,
    start_time=0,
    duration=None,
    tracking_name="match_tracking",
):
    """
    Run YOLO11 + ByteTrack, log coordinates, and save an annotated video.

    Detection and tracking settings (imgsz, conf, tracker, persist) are unchanged.
    Optional start_time/duration seek so frames before the segment are not processed.

    CSV `frame` is the original 1-based video frame index.
    """

    if video_path is None:
        video_path = TEST_VIDEO

    if coordinate_output is None:
        coordinate_output = COORDINATE_OUTPUT

    if max_frames is None:
        max_frames = MAX_FRAMES

    video_path = Path(video_path)
    coordinate_output = Path(coordinate_output)
    start_time = float(start_time or 0)

    fps = _video_fps(video_path)
    start_frame_0 = int(start_time * fps)

    duration_frames = int(float(duration) * fps) if duration is not None else None
    limits = [n for n in (duration_frames, max_frames) if n is not None]
    max_to_process = min(limits) if limits else None
    end_frame_0 = (
        start_frame_0 + max_to_process if max_to_process is not None else None
    )

    identity_manager = IdentityManager()

    print("=" * 60)
    print("Football Analytics - Player Tracking")
    print("=" * 60)

    print(f"Selected device: {DEVICE_LABEL}")
    print(f"Video FPS              : {fps:.4f}")
    print(f"Requested start time   : {start_time:.3f}s")
    print(f"Requested duration     : {duration if duration is not None else 'to end'}")
    print(f"Original start frame 0 : {start_frame_0} (CSV frame {start_frame_0 + 1})")
    if end_frame_0 is not None:
        print(f"Original end frame 0   : {end_frame_0} (exclusive)")
        print(f"Max frames this run    : {max_to_process}")
        if duration_frames is not None and max_frames is not None:
            print("Stop rule: first of --duration / --max-frames / video end")
    else:
        print("Original end frame 0   : video end")

    print(f"Ball predict           : class={BALL_CLASS_ID} conf={BALL_CONFIDENCE} imgsz={BALL_IMGSZ} (no ByteTrack)")

    print("\nLoading YOLO model...")

    model = YOLO(YOLO_MODEL)
    ball_model = YOLO(YOLO_MODEL)

    print("Model loaded successfully!")
    print("Ball detector loaded (separate predictor, same weights).")

    logger = CoordinateLogger(coordinate_output)

    track_dir = TRACKING_OUTPUT / tracking_name
    track_dir.mkdir(parents=True, exist_ok=True)
    annotated_path = track_dir / f"{video_path.stem}.mp4"

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if start_frame_0 >= total_frames:
        cap.release()
        raise RuntimeError(
            f"start-time {start_time}s maps to 0-based frame {start_frame_0}, "
            f"but the video only has {total_frames} frames "
            f"({total_frames / fps:.1f}s). Use a longer source video "
            f"(e.g. videos/raw/match.mp4) or a smaller --start-time."
        )

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame_0)
    actual_pos = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
    if actual_pos != start_frame_0:
        print(
            f"Warning: seek landed at 0-based frame {actual_pos}, "
            f"requested {start_frame_0}"
        )
        if actual_pos > start_frame_0:
            cap.release()
            raise RuntimeError(
                "Seek jumped past the requested start frame. "
                "This often means the requested time is beyond the video length."
            )

    writer = cv2.VideoWriter(
        str(annotated_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )

    start = time.time()
    processed = 0
    first_csv_frame = None
    last_csv_frame = None
    current_0 = actual_pos

    ball_logged = 0
    ball_multi_candidate_frames = 0
    ball_confidences = []

    while True:
        if end_frame_0 is not None and current_0 >= end_frame_0:
            print("Stopping: duration / max-frames limit reached")
            break

        ret, frame = cap.read()
        if not ret:
            print("Stopping: end of video")
            break

        original_frame = current_0 + 1

        results = model.track(
            source=frame,
            tracker=str(TRACKER_CONFIG),
            persist=True,
            save=False,
            device=DEVICE,
            imgsz=1280,
            conf=0.30,
            verbose=False,
        )
        result = results[0]

        identity_manager.start_new_frame()

        if result.boxes is not None:
            for box in result.boxes:
                if box.id is None:
                    continue

                cls = int(box.cls.item())
                cls_name = model.names[cls]
                if cls_name != "person":
                    continue

                track_id = int(box.id.item())
                confidence = float(box.conf.item())
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                position = (
                    int((x1 + x2) / 2),
                    int(y2)
                )
                stable_id = identity_manager.get_stable_id(
                    track_id,
                    original_frame,
                    position,
                    (x1, y1, x2, y2)
                )

                logger.log(
                    frame_number=original_frame,
                    track_id=track_id,
                    stable_id=stable_id,
                    cls_name=cls_name,
                    confidence=round(confidence, 4),
                    x1=x1,
                    y1=y1,
                    x2=x2,
                    y2=y2
                )

        # Ball-only detect: same model, no ByteTrack, no IdentityManager.
        ball_results = ball_model.predict(
            source=frame,
            classes=[BALL_CLASS_ID],
            conf=BALL_CONFIDENCE,
            imgsz=BALL_IMGSZ,
            device=DEVICE,
            verbose=False,
        )
        ball_result = ball_results[0]
        best_ball = None
        ball_candidates = 0
        if ball_result.boxes is not None:
            for box in ball_result.boxes:
                ball_candidates += 1
                confidence = float(box.conf.item())
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                if best_ball is None or confidence > best_ball["confidence"]:
                    best_ball = {
                        "confidence": confidence,
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2,
                    }

        if ball_candidates > 1:
            ball_multi_candidate_frames += 1

        if best_ball is not None:
            cx = (best_ball["x1"] + best_ball["x2"]) / 2.0
            cy = (best_ball["y1"] + best_ball["y2"]) / 2.0
            logger.log(
                frame_number=original_frame,
                track_id=None,
                stable_id=None,
                cls_name=BALL_CLASS_NAME,
                confidence=round(best_ball["confidence"], 4),
                x1=best_ball["x1"],
                y1=best_ball["y1"],
                x2=best_ball["x2"],
                y2=best_ball["y2"],
                bbox_center_x=cx,
                bbox_center_y=cy,
            )
            ball_logged += 1
            ball_confidences.append(best_ball["confidence"])

        annotated = result.plot()
        if best_ball is not None:
            cx = int((best_ball["x1"] + best_ball["x2"]) / 2)
            cy = int((best_ball["y1"] + best_ball["y2"]) / 2)
            cv2.circle(annotated, (cx, cy), 8, (0, 255, 255), -1)
            cv2.circle(annotated, (cx, cy), 12, (0, 0, 0), 2)

        if writer.isOpened():
            writer.write(annotated)

        processed += 1
        if first_csv_frame is None:
            first_csv_frame = original_frame
        last_csv_frame = original_frame
        current_0 += 1

        if processed % 500 == 0:
            print(f"Processed {processed} frames (video frame {original_frame})")

    cap.release()
    writer.release()
    logger.close()

    end = time.time()

    print("\n" + "=" * 60)
    print("Tracking Finished!")
    print("=" * 60)

    print(f"Frames Processed : {processed}")
    if first_csv_frame is not None:
        print(f"CSV frame range  : {first_csv_frame} .. {last_csv_frame}")
        print(
            f"Source time range: "
            f"{(first_csv_frame - 1) / fps:.3f}s .. {last_csv_frame / fps:.3f}s"
        )
    print(f"Time Taken : {end-start:.2f} seconds")
    print(f"Ball rows logged       : {ball_logged}")
    print(f"Frames with >1 ball    : {ball_multi_candidate_frames}")
    if ball_confidences:
        print(
            f"Selected ball conf     : "
            f"min={min(ball_confidences):.3f} "
            f"max={max(ball_confidences):.3f} "
            f"mean={sum(ball_confidences)/len(ball_confidences):.3f}"
        )

    print("\nTracking Output:")
    print(annotated_path)

    print("\nCoordinate File:")
    print(coordinate_output)

    return coordinate_output


if __name__ == "__main__":
    run_tracking()
