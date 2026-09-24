from ultralytics import YOLO
from pathlib import Path
import json
import os
import time

import cv2
import pandas as pd

from config.config import (
    YOLO_MODEL,
    PERSON_MODEL,
    PERSON_IMGSZ,
    PERSON_CONFIDENCE,
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
    IDENTITY_OUTPUT,
    IDENTITY_RESOLVER_ENABLED,
    BALL_OFF_TURF_MIN_CONF,
    GOAL_DETECT_EVERY_S,
    WRITE_DEBUG_VIDEOS,
)

from scripts.coordinate_logger import CoordinateLogger
from scripts.identity.identity_manager import IdentityManager
from scripts.vision.ball_filter import ring_turf_fraction, select_balls
from scripts.vision.camera_motion import CameraMotion, summarize_motion
from scripts.vision.goals import GoalDetector, goal_model_available, goals_path, smooth_goals, write_goals


def camera_summary_path(coordinate_output):
    """Where run_tracking records how much the camera moved."""
    coordinate_output = Path(coordinate_output)
    return coordinate_output.with_name(f"{coordinate_output.stem}_camera.json")


def _apply_identity_resolution(collector, coordinate_output, fps, report_path):
    """
    Replace provisional stable_ids in the coordinate CSV with resolved
    identities and drop non-player person rows (spectators, bench, staff).
    Ball rows are untouched.
    """
    from scripts.identity.resolver import resolve_identities

    t0 = time.time()
    resolution = resolve_identities(collector.as_arrays(), fps)
    report = resolution.report()

    df = pd.read_csv(coordinate_output)
    person = df["class"] == "person"
    track_ids = pd.to_numeric(df["track_id"], errors="coerce")
    identity = track_ids.map(resolution.identity_of)
    keep = ~person | identity.notna()
    df.loc[person, "stable_id"] = identity[person]
    df = df[keep].copy()
    df["stable_id"] = df["stable_id"].astype("Int64")
    df.to_csv(coordinate_output, index=False)

    report["dropped_person_rows"] = int((~keep).sum())
    report["evidence_runtime_s"] = {k: round(v, 1) for k, v in collector.timing.items()}
    report["ocr_calls"] = collector.ocr_calls
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(
        f"Identity resolution    : {report['raw_tracklets']} tracker fragments -> "
        f"{report['player_tracklets']} player fragments -> {report['identities']} identities "
        f"({time.time() - t0:.1f}s)"
    )
    print(f"Non-player rows dropped: {report['dropped_person_rows']}")
    print(
        f"Identity evidence time : ReID {collector.timing['reid_s']:.0f}s, "
        f"OCR {collector.timing['ocr_s']:.0f}s ({collector.ocr_calls} crops)"
    )
    print(f"Identity report        : {report_path}")

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

    With IDENTITY_RESOLVER_ENABLED, stable_id in the written CSV is the
    offline-resolved player identity and non-player person rows are removed.
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

    identity_manager = IdentityManager(fps=fps)

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

    # Separate instances: predict() on the tracking instance would reset ByteTrack.
    model = YOLO(PERSON_MODEL)
    ball_model = YOLO(YOLO_MODEL)

    print(f"Person tracker loaded  : {PERSON_MODEL.name}")
    print(f"Ball detector loaded   : {YOLO_MODEL.name} (separate predictor)")

    # Without the goal model, shots/goals are reported as not measured.
    goal_detector = GoalDetector(DEVICE) if goal_model_available() else None
    goal_every = max(1, int(round(GOAL_DETECT_EVERY_S * fps)))
    goal_detections = {}
    print(f"Goal detector          : {'every %d frames' % goal_every if goal_detector else 'not installed'}")

    collector = None
    if IDENTITY_RESOLVER_ENABLED:
        from scripts.identity.tracklet_features import TrackletFeatureCollector

        collector = TrackletFeatureCollector()
        print("Identity evidence      : ReID + jersey OCR + camera motion (offline resolution)")

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

    writer = None if not WRITE_DEBUG_VIDEOS else cv2.VideoWriter(
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

    camera = CameraMotion()
    camera_transforms = {}
    ball_candidates = []

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
            imgsz=PERSON_IMGSZ,
            conf=PERSON_CONFIDENCE,
            classes=[0],
            verbose=False,
        )
        result = results[0]

        identity_manager.start_new_frame()

        person_boxes = []
        if result.boxes is not None:
            for box in result.boxes:
                if box.id is None:
                    continue
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                person_boxes.append({
                    "track_id": int(box.id.item()),
                    "confidence": float(box.conf.item()),
                    "bbox": (x1, y1, x2, y2),
                    "position": (int((x1 + x2) / 2), int(y2)),
                })

        # Provisional online identity; replaced by offline resolution below
        # when IDENTITY_RESOLVER_ENABLED.
        stable_ids = identity_manager.assign_frame(
            original_frame,
            [
                {"track_id": b["track_id"], "position": b["position"], "bbox": b["bbox"]}
                for b in person_boxes
            ],
            frame=frame,
        )

        camera_transforms[original_frame] = camera.update(frame, [b["bbox"] for b in person_boxes])
        if collector is not None:
            collector.add_frame(original_frame, frame, person_boxes, camera_transforms[original_frame])

        for b in person_boxes:
            x1, y1, x2, y2 = b["bbox"]
            logger.log(
                frame_number=original_frame,
                track_id=b["track_id"],
                stable_id=stable_ids[b["track_id"]],
                cls_name="person",
                confidence=round(b["confidence"], 4),
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
        # Every candidate is kept; the real ball is chosen after tracking,
        # when static look-alikes can be told apart (scripts/vision/ball_filter.py).
        frame_balls = []
        if ball_result.boxes is not None:
            for box in ball_result.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                frame_balls.append({
                    "frame": original_frame,
                    "confidence": float(box.conf.item()),
                    "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                    "turf": ring_turf_fraction(frame, x1, y1, x2, y2),
                })
        ball_candidates.extend(frame_balls)

        if goal_detector is not None and processed % goal_every == 0:
            goal_detections[original_frame] = goal_detector.detect(frame)

        annotated = result.plot() if writer is not None else None
        plausible = [b for b in frame_balls if b["turf"] >= 0.2 or b["confidence"] >= BALL_OFF_TURF_MIN_CONF]
        if plausible and annotated is not None:
            top = max(plausible, key=lambda b: b["confidence"] + 0.15 * (b["turf"] >= 0.2))
            cx, cy = (top["x1"] + top["x2"]) // 2, (top["y1"] + top["y2"]) // 2
            cv2.circle(annotated, (cx, cy), 8, (0, 255, 255), -1)
            cv2.circle(annotated, (cx, cy), 12, (0, 0, 0), 2)

        if writer is not None and writer.isOpened():
            writer.write(annotated)

        processed += 1
        if first_csv_frame is None:
            first_csv_frame = original_frame
        last_csv_frame = original_frame
        current_0 += 1

        if processed % 500 == 0:
            print(f"Processed {processed} frames (video frame {original_frame})")

    cap.release()
    if writer is not None:
        writer.release()

    chosen, ball_stats = select_balls(ball_candidates, camera_transforms, fps)
    for f in sorted(chosen):
        b = chosen[f]
        logger.log(
            frame_number=f,
            track_id=None,
            stable_id=None,
            cls_name=BALL_CLASS_NAME,
            confidence=round(b["confidence"], 4),
            x1=b["x1"],
            y1=b["y1"],
            x2=b["x2"],
            y2=b["y2"],
            bbox_center_x=(b["x1"] + b["x2"]) / 2.0,
            bbox_center_y=(b["y1"] + b["y2"]) / 2.0,
        )
    logger.close()

    motion = summarize_motion(
        [camera_transforms[f] for f in sorted(camera_transforms)], width, height
    )
    camera_summary_path(coordinate_output).write_text(json.dumps(motion, indent=2), encoding="utf-8")

    goal_rows = None
    goal_file = goals_path(coordinate_output)
    if goal_detector is not None:
        goal_rows = smooth_goals(goal_detections, camera_transforms, fps, width, height)
        write_goals(goal_rows, goal_file)
    elif goal_file.exists():
        goal_file.unlink()  # a stale file would pass for this run's goals

    rematch_audit = identity_manager.write_rematch_audit(
        IDENTITY_OUTPUT / "rematch_audit.csv"
    )

    if collector is not None:
        _apply_identity_resolution(
            collector,
            coordinate_output,
            fps,
            IDENTITY_OUTPUT / f"identity_resolution_{coordinate_output.stem}.json",
        )

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
    print(
        f"Ball                   : {ball_stats['frames_with_ball']}/{processed} frames; "
        f"{ball_stats['candidates']} candidates, {ball_stats['static_rejected']} static look-alikes "
        f"and {ball_stats['low_conf_off_turf']} weak off-turf rejected"
    )
    if goal_rows is not None:
        print(f"Goals                  : in view on {len({r['frame'] for r in goal_rows})}/{processed} frames")
    print(
        f"Camera                 : {'moving' if motion['moving'] else 'fixed'} "
        f"(pan {motion['pan_x_px']:.0f}x{motion['pan_y_px']:.0f}px, zoom x{motion['zoom_ratio']:.2f})"
    )

    print("\nTracking Output:")
    print(annotated_path)

    print("\nCoordinate File:")
    print(coordinate_output)

    if rematch_audit:
        print(f"Rematch audit        : {rematch_audit}")

    return coordinate_output


if __name__ == "__main__":
    run_tracking()
