from pathlib import Path

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

# ======================================================
# TRACKER
# ======================================================

TRACKER_CONFIG = PROJECT_ROOT / "config" / "bytetrack.yaml"

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

]

for folder in folders:
    folder.mkdir(parents=True, exist_ok=True)

print("Configuration Loaded Successfully!")