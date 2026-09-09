from pathlib import Path
import torch

# ======================================================
# PROJECT ROOT
# ======================================================

PROJECT_ROOT = Path(r"D:\FootballAnalytics")

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

OUTPUT_DIR = PROJECT_ROOT / "outputs"

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

]

for folder in folders:
    folder.mkdir(parents=True, exist_ok=True)

print("Configuration Loaded Successfully!")