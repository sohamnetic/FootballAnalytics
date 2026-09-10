from pathlib import Path
import os
import torch

# ======================================================
# PROJECT ROOT
# ======================================================

PROJECT_ROOT = Path(r"D:\FootballAnalytics")

# Product jobs may isolate outputs via FA_OUTPUT_DIR without changing engines.
# Unset = existing CLI behaviour (PROJECT_ROOT / "outputs").

# ======================================================
# MODELS
# ======================================================

MODELS_DIR = PROJECT_ROOT / "models"
YOLO_MODEL = MODELS_DIR / "yolo11n.pt"

# ======================================================
# VIDEOS
# ======================================================

VIDEOS_DIR = PROJECT_ROOT / "videos"

RAW_VIDEO = VIDEOS_DIR / "raw" / "match.mp4"

TEST_VIDEO = VIDEOS_DIR / "test" / "match_test.mp4"

CHUNKS_DIR = VIDEOS_DIR / "chunks"

# ======================================================
# OUTPUTS
# ======================================================

_output_override = os.environ.get("FA_OUTPUT_DIR", "").strip()
OUTPUT_DIR = Path(_output_override) if _output_override else (PROJECT_ROOT / "outputs")

DETECTION_OUTPUT = OUTPUT_DIR / "detections"

TRACKING_OUTPUT = OUTPUT_DIR / "tracking"

COORDINATE_OUTPUT = OUTPUT_DIR / "coordinates"

HEATMAP_OUTPUT = OUTPUT_DIR / "heatmaps"

EVENTS_OUTPUT = OUTPUT_DIR / "events"

# Phase 1 possession (pixel space; frames not seconds)
MAX_BALL_INTERPOLATION_GAP = 15
MAX_POSSESSION_DISTANCE_PX = 150
POSSESSION_CONFIRM_FRAMES = 5

# Ball-only YOLO predict (COCO sports ball). Does not affect player track().
BALL_CLASS_ID = 32
BALL_CLASS_NAME = "sports ball"
BALL_CONFIDENCE = 0.10
BALL_IMGSZ = 1280

# Identity rematch (person only). Distance stays conservative; gap widened.
IDENTITY_OUTPUT = OUTPUT_DIR / "identity"
IDENTITY_MAX_FRAME_GAP = 150
IDENTITY_MAX_DISTANCE_PX = 120
# Reject rematch only when BOTH sides have jersey colour and BGR distance exceeds this.
IDENTITY_APPEARANCE_MAX_BGR_DIST = 80
IDENTITY_REMATCH_AUDIT = True

# Team assignment from jersey colour (not player identity)
TEAM_OUTPUT = OUTPUT_DIR / "teams"
TEAM_MIN_SAMPLES = 8
TEAM_DET_MIN_CONFIDENCE = 0.45
TEAM_SAMPLE_STRIDE = 5
TEAM_MAX_SAMPLES_PER_ID = 40
TEAM_ASSIGN_MIN_CONFIDENCE = 0.35
TEAM_AMBIGUOUS_RATIO = 0.88
TEAM_REFEREE_MIN_CENTROID_DIST = 0.45

# Pass detection (post-process of frame_state + team assignment)
PASS_MAX_TRANSITION_FRAMES = 30
PASS_MIN_POSSESSION_FRAMES = 5
PASS_MAX_MISSING_BALL_RATIO = 0.50

# Interceptions / recoveries (post-process; do not change pass logic)
INTERCEPTION_MAX_TRANSITION_FRAMES = 30
RECOVERY_MAX_TRANSITION_FRAMES = 30

# Shots / on-target / goals (post-process; camera PIXEL space, not metres)
# Goal zones are axis-aligned boxes (x1, y1, x2, y2) in the 1920x1080 camera frame.
# LEFT mouth: traced from the visible 5-a-side goal in roi_validation (not ROI corners).
# RIGHT mouth: approximate opposite-end box near the right pitch edge; the far goal is
# not fully framed. Edit these if the camera is recropped or sides are wrong.
GOAL_ZONE_LEFT = (150, 165, 370, 760)
GOAL_ZONE_RIGHT = (1570, 180, 1910, 860)
# Which team defends which goal. Shooter attacks the opposite zone.
TEAM_DEFENDS_GOAL = {"team_a": "left", "team_b": "right"}

SHOT_MAX_TRANSITION_FRAMES = 60
SHOT_MIN_BALL_MOVEMENT_PX = 80
SHOT_GOAL_APPROACH_WINDOW_FRAMES = 90
SHOT_MIN_POSSESSION_FRAMES = 5
SHOT_MAX_MISSING_BALL_RATIO = 0.55
SHOT_MIN_GOAL_APPROACH_PX = 25
SHOT_ON_TARGET_MAX_DIST_PX = 45
SHOT_GOAL_INSIDE_FRAMES = 2
SHOT_WRITE_VALIDATION_VIDEO = True

# ======================================================
# TRACKER
# ======================================================

TRACKER_CONFIG = PROJECT_ROOT / "config" / "bytetrack.yaml"

# ======================================================
# DEVICE (CUDA if available, otherwise CPU)
# ======================================================

if torch.cuda.is_available():
    DEVICE = 0
    DEVICE_LABEL = "CUDA:0"
else:
    DEVICE = "cpu"
    DEVICE_LABEL = "CPU"

# ======================================================
# CREATE MISSING FOLDERS
# ======================================================

folders = [

    MODELS_DIR,

    VIDEOS_DIR,

    CHUNKS_DIR,

    OUTPUT_DIR,

    DETECTION_OUTPUT,

    TRACKING_OUTPUT,

    COORDINATE_OUTPUT,

    HEATMAP_OUTPUT,

    EVENTS_OUTPUT,

    IDENTITY_OUTPUT,

    TEAM_OUTPUT,

]

for folder in folders:
    folder.mkdir(parents=True, exist_ok=True)

print("Configuration Loaded Successfully!")