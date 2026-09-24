from pathlib import Path
import os
import torch

# ======================================================
# PROJECT ROOT
# ======================================================

PROJECT_ROOT = Path(r"D:\FootballAnalytics")

# set FA_OUTPUT_DIR to write a job's outputs somewhere else (the web app does this)

# ======================================================
# MODELS
# ======================================================

MODELS_DIR = PROJECT_ROOT / "models"
# ball detector - events were tuned on the nano model
YOLO_MODEL = MODELS_DIR / "yolo11n.pt"
# players - nano lost people too often and broke up their ids
PERSON_MODEL = MODELS_DIR / "yolo11m.pt"
PERSON_IMGSZ = 1280
PERSON_CONFIDENCE = 0.30

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

# ------------------------------------------------------
# All the *_S values below are seconds, converted to frames with the
# video's fps (see scripts/analytics/events/timing.py)
# ------------------------------------------------------

# Possession
# distances are in "body heights" (BH) = the player's box height, so they
# don't change when the camera zooms. 0.75 BH is roughly 1.3 m
MAX_BALL_INTERPOLATION_GAP_S = 0.25
POSSESSION_MAX_DISTANCE_BH = 0.75
# the player who has the ball keeps it unless someone is clearly closer
POSSESSION_CHALLENGE_RATIO = 0.6
# ball has to move with the player, otherwise it's just flying past them
POSSESSION_MAX_REL_SPEED_BH_S = 4.0
POSSESSION_SPEED_WINDOW_S = 0.067
# same player losing the ball for a moment (dribbling) = still one possession
POSSESSION_MERGE_GAP_S = 1.0
POSSESSION_CONFIRM_S = 0.08

# Ball detection (COCO "sports ball", no tracker)
BALL_CLASS_ID = 32
BALL_CLASS_NAME = "sports ball"
BALL_CONFIDENCE = 0.10
BALL_IMGSZ = 1280
# a "ball" that's not on the turf needs a bit more confidence
BALL_OFF_TURF_MIN_CONF = 0.20

# Online identity (identity_manager.py). Only used as the final id when the
# offline resolver below is turned off.
# Max jump allowed when re-matching a lost player:
#   min(BASE_SLACK + gap_frames * PX_PER_SECOND / fps, CEILING)
# numbers were picked by looking at real player movement in the 40s clip
IDENTITY_OUTPUT = OUTPUT_DIR / "identity"
IDENTITY_MAX_GAP_S = 3.67
IDENTITY_BASE_SLACK_PX = 40.0
IDENTITY_PX_PER_SECOND_BUDGET = 1080.0
IDENTITY_MAX_DISTANCE_CEILING_PX = 550.0
# only check shirt colour for longer gaps, short ones are fine on position alone
IDENTITY_APPEARANCE_MIN_GAP_S = 0.33
IDENTITY_APPEARANCE_MAX_HIST_DIST = 0.55
IDENTITY_MAX_HEIGHT_RATIO = 2.0
IDENTITY_HEIGHT_RATIO_MIN_SAMPLES = 6
IDENTITY_REMATCH_AUDIT = True

# Offline identity (resolver.py) - joins tracker fragments into players using
# ReID, shirt numbers and movement. Also drops people who aren't players.
IDENTITY_RESOLVER_ENABLED = True
IDENTITY_REID_WEIGHTS = MODELS_DIR / "lmbn_n_duke.pt"
IDENTITY_REID_EVERY = 10                # run ReID every 10th frame
IDENTITY_OCR_ENABLED = True
IDENTITY_OCR_EVERY = 8                  # OCR every 8th usable crop of a track
IDENTITY_OCR_MAX_PER_TRACK = 400        # just a safety limit, it stops earlier once the number is clear
IDENTITY_OCR_MIN_HEIGHT_PX = 90         # smaller than this and the number is unreadable
IDENTITY_OCR_MIN_CONF = 0.35
# turf colour in OpenCV HSV. min V is 80 because the bench mat is the same green but darker
IDENTITY_TURF_HSV_MIN = (35, 60, 80)
IDENTITY_TURF_HSV_MAX = (56, 255, 255)
IDENTITY_MIN_TRACKLET_DETECTIONS = 10
# who counts as a player: on the turf with a coloured kit, or near the
# boards with a very bright kit (ref / keepers)
IDENTITY_PLAYER_TURF_MIN = 0.55
IDENTITY_KIT_MIN_SAT = 0.45
IDENTITY_PLAYER_TURF_MIN_STRONG_KIT = 0.30
IDENTITY_STRONG_KIT_SAT = 0.80
IDENTITY_STABILIZED_SPEED_PX_S = 900.0
IDENTITY_MERGE_COST = 0.35
IDENTITY_FORCED_MERGE_COST = 0.80       # used only while a kit still has too many ids

# Teams
TEAM_OUTPUT = OUTPUT_DIR / "teams"
TEAM_MIN_SAMPLES = 8
TEAM_DET_MIN_CONFIDENCE = 0.45
TEAM_SAMPLE_STRIDE = 5
TEAM_MAX_SAMPLES_PER_ID = 40
TEAM_ASSIGN_MIN_CONFIDENCE = 0.35
TEAM_AMBIGUOUS_RATIO = 0.88
TEAM_REFEREE_MIN_CENTROID_DIST = 0.45
# not in either team kit + mostly standing near a goal = goalkeeper, else referee
GOALKEEPER_NEAR_GOAL_GH = 2.5
GOALKEEPER_MIN_NEAR_GOAL_SHARE = 0.6

# Passes - a 10-20 m pass takes 1-2 s to arrive
PASS_MAX_TRANSITION_S = 2.0
PASS_MIN_POSSESSION_S = 0.08
PASS_MAX_MISSING_BALL_RATIO = 0.50

# Interceptions / recoveries
INTERCEPTION_MAX_TRANSITION_S = 2.0
RECOVERY_MAX_TRANSITION_S = 2.0

# Goal detection (scripts/vision/goals.py)
GOAL_MODEL = MODELS_DIR / "goal_yolo11n.pt"
GOAL_IMGSZ = 1280
GOAL_CONFIDENCE = 0.25
GOAL_DETECT_EVERY_S = 0.1
GOAL_SMOOTH_WINDOW_S = 0.5
GOAL_MIN_SUPPORT = 2            # need this many detections of a goal
GOAL_STRONG_CONFIDENCE = 0.6    # or one this confident

# Shots / goals
# GH = goal box height (~2 m), BH/s = shooter body heights per second
SHOT_MIN_POSSESSION_S = 0.08
SHOT_WINDOW_S = 1.5             # how long we follow the ball after the kick
SHOT_AIM_S = 0.4                # direction is taken from this first part
SHOT_MIN_SPEED_BH_S = 3.0       # ~5.5 m/s
SHOT_MAX_SPEED_BH_S = 15.0      # anything faster is a bad ball detection
SHOT_MAX_BALL_TO_SHOOTER_BH = 1.0
SHOT_MAX_AIM_ANGLE_DEG = 45.0
SHOT_MIN_APPROACH_GH = 0.25
SHOT_MAX_START_GH = 10.0        # ~20 m, further than that it's a clearance
SHOT_AIM_MARGIN = 0.75          # how wide of the goal still counts as a shot (in goal widths)
SHOT_NEAR_GOAL_GH = 1.5
GOAL_INSIDE_INSET = 0.15
GOAL_FREE_BALL_MARGIN = 0.25    # no player right next to the ball in the net
GOAL_MIN_INSIDE_S = 0.3
GOAL_VANISH_S = 1.0             # ball disappears in the net for this long

# Analysis video shown on the dashboard, needs ffmpeg
FFMPEG_BIN = os.environ.get("FA_FFMPEG", "").strip() or None
ANALYSIS_VIDEO_WIDTH = 1280
ANALYSIS_VIDEO_CRF = 24
ANALYSIS_VIDEO_PRESET = "veryfast"
# old per-step debug videos, big and browsers can't play them. FA_DEBUG_VIDEOS=1 to turn on
WRITE_DEBUG_VIDEOS = os.environ.get("FA_DEBUG_VIDEOS", "").strip() == "1"

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
