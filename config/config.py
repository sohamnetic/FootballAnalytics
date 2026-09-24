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
# Ball detection keeps the nano model (event engines were tuned on it).
YOLO_MODEL = MODELS_DIR / "yolo11n.pt"
# Person tracking uses the medium model: the nano model dropped players for
# longer than the tracker buffer often enough to fragment identities.
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
# Event timing is in SECONDS and converted to frames per video
# (scripts/analytics/events/timing.py). These were frame counts tuned on
# 59.94 fps footage; as frame counts they silently doubled every time
# window on 30 fps uploads. Values below equal the old counts at 59.94 fps.
# ------------------------------------------------------

# Possession. Ball-to-feet distance is measured in the player's own body
# heights (box height), so it means the same thing at any zoom: 0.75 BH is
# ~1.3 m, and equals the old fixed 150 px for a median-sized player.
MAX_BALL_INTERPOLATION_GAP_S = 0.25
POSSESSION_MAX_DISTANCE_BH = 0.75
# While the current possessor is still in range, a challenger must be clearly
# closer (this share of the possessor's distance) to take the ball, so two
# players contesting it don't flicker possession back and forth.
POSSESSION_CHALLENGE_RATIO = 0.6
# A ball flying past a player is not possessed: the ball must move with the
# player (relative speed over +-POSSESSION_SPEED_WINDOW_S, in body heights/s;
# 4 BH/s ~ 7 m/s). Measured on the 5-min upload: spells of 6+ frames have a
# median of ~1 BH/s, 1-5 frame "spells" ~10 BH/s.
POSSESSION_MAX_REL_SPEED_BH_S = 4.0
POSSESSION_SPEED_WINDOW_S = 0.067
# One player's spells split by up to this gap are one possession (dribbling).
POSSESSION_MERGE_GAP_S = 1.0
POSSESSION_CONFIRM_S = 0.08

# Ball-only YOLO predict (COCO sports ball). Does not affect player track().
BALL_CLASS_ID = 32
BALL_CLASS_NAME = "sports ball"
BALL_CONFIDENCE = 0.10
BALL_IMGSZ = 1280
# Candidates off the turf (a ball in the air) need more confidence; static
# off-turf look-alikes (wall fittings, signs) are rejected outright.
# See scripts/vision/ball_filter.py.
BALL_OFF_TURF_MIN_CONF = 0.20

# Provisional online identity (scripts/identity/identity_manager.py). Only the
# final stable_id when IDENTITY_RESOLVER_ENABLED is False; otherwise the
# offline resolver further below replaces it.
#
# Position gate is adaptive, not a flat radius: allowed_px = min(
#   IDENTITY_BASE_SLACK_PX + frame_gap * (IDENTITY_PX_PER_SECOND_BUDGET / fps),
#   IDENTITY_MAX_DISTANCE_CEILING_PX,
# )
# IDENTITY_PX_PER_SECOND_BUDGET is calibrated from observed frame-to-frame
# player displacement on outputs/coordinates/match_t200_d40.csv (~18 px at
# 59.94 fps, between the 95th/99th percentile of real single-track motion).
# A flat threshold under-allows long gaps and over-allows short ones; this
# scales with elapsed time and is capped so a long gap still can't match
# across implausible pitch-crossing distances. See docs/architecture.md.
#
# Appearance gate is a two-region (upper/lower) HS histogram, not a single
# mean-BGR sample (much less sensitive to lighting/motion blur/shadow), and
# is only enforced once the gap is large enough that geometry alone is
# unreliable (short gaps stay geometry-only to avoid rejecting good matches
# on appearance noise). It is calibrated against real same-player vs
# different-player histogram-distance distributions on the same clip.
IDENTITY_OUTPUT = OUTPUT_DIR / "identity"
IDENTITY_MAX_GAP_S = 3.67
IDENTITY_BASE_SLACK_PX = 40.0
IDENTITY_PX_PER_SECOND_BUDGET = 1080.0
IDENTITY_MAX_DISTANCE_CEILING_PX = 550.0
IDENTITY_APPEARANCE_MIN_GAP_S = 0.33
IDENTITY_APPEARANCE_MAX_HIST_DIST = 0.55
# Cheap sanity gate: reject if bbox-height ratio is too extreme. Only
# applied once a profile has enough samples that its average height isn't
# just one noisy detection.
IDENTITY_MAX_HEIGHT_RATIO = 2.0
IDENTITY_HEIGHT_RATIO_MIN_SAMPLES = 6
IDENTITY_REMATCH_AUDIT = True

# Offline identity resolution (scripts/identity/resolver.py): after tracking,
# raw tracker fragments are merged into player identities using person-ReID
# embeddings, jersey-number OCR, camera-motion-compensated continuity, and
# hard constraints (co-visible fragments / different kits never merge).
# Non-players (spectators, bench, staff) are dropped by a turf + kit gate.
# Thresholds were validated against hand-checked identities on the
# 40s reference clip (videos/raw/match.mp4 @ 200s); see docs/architecture.md.
IDENTITY_RESOLVER_ENABLED = True
IDENTITY_REID_WEIGHTS = MODELS_DIR / "lmbn_n_duke.pt"
IDENTITY_REID_EVERY = 10                # embed everyone on every Nth frame (one batched call)
IDENTITY_OCR_ENABLED = True
IDENTITY_OCR_EVERY = 8                  # OCR every Nth eligible crop over the track's whole life;
IDENTITY_OCR_MAX_PER_TRACK = 400        # stops early once the number is settled (runtime guard only)
IDENTITY_OCR_MIN_HEIGHT_PX = 90         # numbers are unreadable on smaller boxes
IDENTITY_OCR_MIN_CONF = 0.35
# Artificial turf in OpenCV HSV. The bench mat beside this pitch is the same
# hue but much darker (V 56-77 vs turf 85-140), hence the V floor.
IDENTITY_TURF_HSV_MIN = (35, 60, 80)
IDENTITY_TURF_HSV_MAX = (56, 255, 255)
IDENTITY_MIN_TRACKLET_DETECTIONS = 10
# Player gate: on turf with a saturated kit, or near the boards (lower turf
# score) with a strongly saturated kit (referee / keepers).
IDENTITY_PLAYER_TURF_MIN = 0.55
IDENTITY_KIT_MIN_SAT = 0.45
IDENTITY_PLAYER_TURF_MIN_STRONG_KIT = 0.30
IDENTITY_STRONG_KIT_SAT = 0.80
IDENTITY_STABILIZED_SPEED_PX_S = 900.0
IDENTITY_MERGE_COST = 0.35              # confident merges
IDENTITY_FORCED_MERGE_COST = 0.80       # only while a kit has more ids than its max-concurrent headcount

# Team assignment from jersey colour (not player identity)
TEAM_OUTPUT = OUTPUT_DIR / "teams"
TEAM_MIN_SAMPLES = 8
TEAM_DET_MIN_CONFIDENCE = 0.45
TEAM_SAMPLE_STRIDE = 5
TEAM_MAX_SAMPLES_PER_ID = 40
TEAM_ASSIGN_MIN_CONFIDENCE = 0.35
TEAM_AMBIGUOUS_RATIO = 0.88
TEAM_REFEREE_MIN_CENTROID_DIST = 0.45
# A player outside both team kits is a goalkeeper if their feet are within
# this many goal-box heights of a goal for this share of the time a goal is
# in view; otherwise the referee.
GOALKEEPER_NEAR_GOAL_GH = 2.5
GOALKEEPER_MIN_NEAR_GOAL_SHARE = 0.6

# Pass detection (post-process of frame_state + team assignment).
# Ball travel time between passer and receiver: a 10-20 m pass on a 5-a-side
# pitch takes 1-2 s (0.5 s, tuned on a short clip, rejected most real passes).
PASS_MAX_TRANSITION_S = 2.0
PASS_MIN_POSSESSION_S = 0.08
PASS_MAX_MISSING_BALL_RATIO = 0.50

# Interceptions / recoveries (post-process; do not change pass logic)
INTERCEPTION_MAX_TRANSITION_S = 2.0
RECOVERY_MAX_TRANSITION_S = 2.0

# Goals (posts + net) are detected in the video, not configured: the camera
# pans and zooms, so the goals move around the image (scripts/vision/goals.py).
GOAL_MODEL = MODELS_DIR / "goal_yolo11n.pt"
GOAL_IMGSZ = 1280
GOAL_CONFIDENCE = 0.25
GOAL_DETECT_EVERY_S = 0.1
GOAL_SMOOTH_WINDOW_S = 0.5
GOAL_MIN_SUPPORT = 2            # detection frames agreeing on a goal...
GOAL_STRONG_CONFIDENCE = 0.6    # ...unless one detection is this sure

# Shots / goals (post-process). Ball motion is measured relative to the goal
# box of the same frame, so camera pans cancel out; distances are in goal
# box heights (GH) and speeds in shooter body heights per second (BH/s),
# so zoom cancels out too.
SHOT_MIN_POSSESSION_S = 0.08
SHOT_WINDOW_S = 1.5             # ball flight watched after the shooter's touch
SHOT_AIM_S = 0.4                # first part of the flight sets the direction
SHOT_MIN_SPEED_BH_S = 3.0       # a shot is struck, not rolled (~5.5 m/s)
SHOT_MAX_SPEED_BH_S = 15.0      # ~27 m/s; faster is the ball track jumping between objects
SHOT_MAX_BALL_TO_SHOOTER_BH = 1.0
SHOT_MAX_AIM_ANGLE_DEG = 45.0   # ball travel vs direction to the goal centre
SHOT_MIN_APPROACH_GH = 0.25     # the ball must end up at least this much closer
SHOT_MAX_START_GH = 10.0        # ~20 m: further out is a clearance / long ball
SHOT_AIM_MARGIN = 0.75          # aim may miss the box by this x box width (wide shots)
SHOT_NEAR_GOAL_GH = 1.5         # a shot must reach this close unless blocked / saved
GOAL_INSIDE_INSET = 0.15        # ball must be this far inside the box edges
GOAL_FREE_BALL_MARGIN = 0.25    # ...and not on or beside a player (box widened by this x its width)
GOAL_MIN_INSIDE_S = 0.3         # ball stays in the net at least this long...
GOAL_VANISH_S = 1.0             # ...or disappears in the net for this long

# Analysis video for the dashboard (scripts/analytics/analysis_video.py):
# H.264 via ffmpeg (FA_FFMPEG, else ffmpeg on PATH); skipped without it.
FFMPEG_BIN = os.environ.get("FA_FFMPEG", "").strip() or None
ANALYSIS_VIDEO_WIDTH = 1280
ANALYSIS_VIDEO_CRF = 24
ANALYSIS_VIDEO_PRESET = "veryfast"
# Per-stage debug overlays (tracking, possession, teams, shots): OpenCV
# MPEG-4 files browsers can't play, ~0.5-0.9 GB each per 5 minutes. Off
# unless debugging; the analysis video replaces them in the product.
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