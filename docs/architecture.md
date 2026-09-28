# Football Analytics â€” Architecture

**Source of truth:** repository code, not README claims.  
Companion docs: `PROJECT_TECHNICAL_AUDIT.md`, `AI_HANDOFF_CONTEXT.md`, `INTERVIEW_PREPARATION.md`, `RESUME_PROJECT_DESCRIPTION.md`.  
On Windows this path may be the same file as `docs/architecture.md` (case-insensitive disk).  
**Coordinate space of events:** camera pixels, but distances are relative to something in the same frame: player body heights (BH) for possession, goal-box heights (GH) for shots. No homography / metres.  
**Camera:** the reference footage and the uploads are **panning/zooming** broadcast-style cameras, not fixed ones. Anything in raw pixels (fixed goal boxes, the ROI quad, fixed pixel distances) only holds for the camera pose it was drawn on, so the event path no longer uses any (see *Goals, shots and possession on a moving camera*).  
**Identity:** `stable_id` is an offline-resolved player identity (see *Identity resolution* below), validated on the 40s reference clip. It is still an estimate, not a guaranteed real-world ID.

## System diagram (actual)

```
User (browser)
  â†’ React/Vite frontend (:5173)
      â†’ fetch /api/*  (Vite proxy â†’ FastAPI :8000)
          â†’ data/uploads/{match_id}/video.*
          â†’ data/matches_index.json  (match metadata)
          â†’ data/users.json          (accounts)
          â†’ background worker (1 daemon thread)
              â†’ subprocess: python -m scripts.pipeline.run_mvp
                  FA_OUTPUT_DIR=outputs/matches/{match_id}
                  --video uploaded file --force-track
                  [optional --start-time --duration]
              â†’ YOLO11m + ByteTrack (persons, buffer 90)
              â†’ YOLO11n predict class 32 (ball, no tracker) â†’ ball_filter (static look-alikes)
              â†’ goal_yolo11n every 0.1 s (goal posts + net) â†’ goals tracked through camera motion
              â†’ IdentityManager (provisional online stable_id)
              â†’ TrackletFeatureCollector (turf, kit, ReID, OCR, camera motion)
              â†’ CoordinateLogger CSV
              â†’ resolve_identities â†’ CSV stable_id rewritten, non-players dropped
              â†’ MotionEngine + HeatmapEngine
              â†’ PossessionEngine â†’ frame_state CSV
              â†’ team_assigner (identity kit groups; goalkeepers by goal proximity; referee excluded)
              â†’ passes / turnovers / shots (post-process; shots against detected goals)
              â†’ match_stats.json
              â†’ analysis video (H.264 via ffmpeg) for the dashboard's Tracking view
          â†’ GET /api/matches/{id}/stats
  â†’ Dashboard renders JSON
```

## Stage-by-stage (verified)

| Stage | File | Function/class | Exists? |
|---|---|---|---|
| Video input | `frontend/src/pages/UploadPage.tsx`, `app/main.py` | `upload_match` | Yes |
| Player detection | `scripts/track.py` | `yolo11m` `YOLO.track` `imgsz=1280` `conf=0.30` `classes=[0]` | Yes |
| Ball detection | `scripts/track.py`, `scripts/vision/ball_filter.py` | `yolo11n` `ball_model.predict` `classes=[32]` `conf=0.10` `imgsz=1280`; `select_balls` | Yes |
| Goal detection | `scripts/vision/goals.py` | `GoalDetector` (`models/goal_yolo11n.pt`), `smooth_goals` | Yes |
| Tracking | Ultralytics ByteTrack | `config/bytetrack.yaml` `persist=True`, track buffer 1.5 s (`TRACK_BUFFER_S`) | Yes |
| Identity (provisional) | `scripts/identity/identity_manager.py` | `IdentityManager.assign_frame` | Yes |
| Identity (final) | `scripts/identity/tracklet_features.py`, `resolver.py` | `TrackletFeatureCollector`, `resolve_identities` | Yes |
| Coordinate log | `scripts/coordinate_logger.py` | `CoordinateLogger.log` | Yes |
| Motion/heatmaps | `scripts/analytics/motion_engine.py`, `heatmap.py` | pixel trajectory | Yes |
| Possession | `scripts/analytics/events/possession.py` | `PossessionEngine` | Yes |
| Teams | `scripts/vision/team_assigner.py` | `assign_teams_by_kit` (fallback: `assign_teams` k-means) | Yes |
| Passes | `scripts/analytics/events/passes.py` | `classify_transition` | Yes |
| Intercept/recovery | `scripts/analytics/events/turnovers.py` | `classify_turnover_pair` | Yes |
| Shots/on-target/goal | `scripts/analytics/events/shots.py` | `classify_shot` | Yes |
| Match stats | `scripts/analytics/match_stats.py` | `build_match_stats` | Yes |
| Analysis video | `scripts/analytics/analysis_video.py` | `render_analysis_video` (ffmpeg libx264) | Yes |
| API | `app/main.py` | FastAPI | Yes |
| Frontend dashboard | `frontend/src/pages/DashboardPage.tsx` | consumes JSON only | Yes |
| Homography / metres | â€” | â€” | **NOT IMPLEMENTED** in event path |
| Broadcast xG / tackles / assists | â€” | â€” | **NOT IMPLEMENTED** |
| Dashboard playback of match video | `frontend/src/components/dashboard/VideoCard.tsx` | Footage / Tracking (analysis video) toggle | Yes |

## Data stores

Web app files go through `app/storage.py`: a folder (`data/`) locally, or x, see `docs/DEPLOY.md`).

| Key (under `data/` locally) | Role |
|---|---|
| `uploads/{uuid}/video.ext` | Original upload (deleted after analysis in the cloud) |
| `results/{uuid}/match_stats.json` | Stats the dashboard reads |
| `results/{uuid}/analysis_video.mp4` | Dashboard "Tracking" video |
| `results/{uuid}/pipeline.log` | Last 600 lines the pipeline printed |
| `matches_index.json` | Match list (not a database; the API is the only writer) |
| `users.json` | Accounts |
| `worker_state.json` | When the cloud worker was last started / seen |
| `data/secret.txt` | HMAC token secret, local only (`FA_SECRET` in the cloud) |
| `outputs/` | Default CLI outputs |
| `outputs/matches/{match_id}/` | Working folder of a local analysis run (`FA_OUTPUT_DIR`) |
| `models/yolo11n.pt` | Ultralytics YOLO11n COCO weights |
| `models/goal_yolo11n.pt` | Goal detector fine-tuned in this repo (committed; not downloadable) |
| `<coordinates>/<stem>_goals.csv` | Goal boxes per frame (written by tracking) |
| `<coordinates>/<stem>_camera.json` | Camera pan/zoom summary |
| `outputs/matches/{id}/analysis/analysis_video.mp4` | Dashboard "Tracking" video: H.264 720p, ~65 MB per 5 min |

## Important architectural decisions (code-backed)

1. **Two YOLO instances** in `run_tracking`: `model.track` for persons and `ball_model.predict` for sports ball. Comments and prior bugs: sharing one instance resets ByteTrack.
2. **Ball is not ByteTracked** and has empty `track_id` / `stable_id`.
3. **Events are post-process** on `frame_state.csv` + teams. They do not run inside the YOLO loop.
4. **Possession % in match_stats** is share of *confirmed team possession seconds*, forced to sum to 100% (`a_pct` and `100 - a_pct`). It is **not** share of full clip time.
5. **Goal geometry** is detected in the video (posts + net) and tracked through camera pans; nothing is configured per camera.
6. **Product jobs** wrap CLI via subprocess + `FA_OUTPUT_DIR`; they do not reimplement engines.
7. **Auth** is local PBKDF2 + HMAC tokens, not OAuth/JWT library.

## Coordinate conventions

| Entity | `center_x` / `center_y` in CSV |
|---|---|
| Person | bbox bottom-centre: `((x1+x2)/2, y2)` â€” used as â€œfeetâ€ |
| Ball | geometric bbox centre, passed as `bbox_center_x/y` |

`time_s` in frame_state: `(frame - 1) / fps`.

## What PitchMapper actually does

`scripts/analytics/pitch_mapper.py` scales `center_x/1920`, `center_y/1080` onto `assets/pitch.png`. It is **not** used by possession, passes, shots, or match_stats. `data/pitch/pitch_dimensions.py` (40Ã—20 m) is **unused** by the event pipeline.

ROI `data/roi/camera_001.json` is a pitch quadrilateral in image pixels for one camera pose; with a panning camera it does not track the pitch and is **not** used to filter people or for shots.

## Identity resolution (2026-09-23)

**Why fragments happen.** On the 40s reference clip ByteTrack produced
~90-110 track ids for 13 people on the pitch. Diagnosis of track ends:
~40% were players leaving the view as the camera panned (no online tracker
can bridge that), ~35% were mid-frame detector dropouts longer than the
tracker buffer, the rest occlusions. Roughly half of all tracks were not
players at all (spectators, bench, staff, board logos, netting).

**At the source.** Person tracking uses `yolo11m` (fewer dropouts than
`yolo11n`) with a ByteTrack buffer of 1.5 s (`TRACK_BUFFER_S`; 90 frames at 60 fps). BoT-SORT's camera-motion
compensation was tested and did not reduce fragments (pans are slow; the
losses are exits and dropouts), so ByteTrack stays.

**Evidence collected inline** (`scripts/identity/tracklet_features.py`,
same decode as tracking, no second video pass):

| Evidence | How | Used for |
|---|---|---|
| Turf score | fraction of turf-coloured pixels in a band around the feet (`IDENTITY_TURF_HSV_*`) | player vs spectator/bench |
| Kit hue + saturation | torso hue histogram, turf pixels excluded | kit group; "wears a kit at all" |
| Person ReID | LMBN (DukeMTMC) via boxmot, every `IDENTITY_REID_EVERY_S` | appearance similarity |
| Jersey number | EasyOCR digits, every `IDENTITY_OCR_EVERY_S` per track on boxes >= 90px, capped per track | strongest same/different evidence |
| Camera motion | background optical flow -> similarity transform chained to frame 1 | pan-compensated positions |

**Resolution** (`scripts/identity/resolver.py`, runs at the end of
`run_tracking`, rewrites `stable_id` in the coordinate CSV and drops
non-player person rows; report in `outputs/.../identity/identity_resolution_*.json`):

1. *Player gate*: at least `IDENTITY_MIN_TRACKLET_S` of detections and (turf >= 0.55 with kit saturation
   >= 0.45, or turf >= 0.30 with saturation >= 0.80 for the referee/keepers
   near the boards).
2. *Kit group*: dominant torso hue bin. Different kits never merge.
3. *Constrained agglomerative clustering* over tracklets. Cost = average-
   linkage ReID distance, minus 0.30 when both sides carry the same
   confident jersey number (0.10 for a partial read), plus a penalty when
   the pan-compensated jump between consecutive fragments is implausible.
   Hard cannot-links: visible at the same time as clearly different boxes
   (overlap with IoU >= 0.5 is treated as a duplicate/merged box, not two
   people), different kit group, confidently different numbers (OCR `7` is
   normalised to `1`; partial reads like `2` vs `12` are compatible).
   Confident merges up to cost 0.35; then, per kit, forced merges up to 0.80
   only while the kit has more identities than its maximum concurrent
   headcount.

**Validated result (40s clip, 200-240s).** End-to-end
`run_mvp --video videos/raw/match.mp4 --start-time 200 --duration 40`:
90 raw ByteTrack ids -> 35 player tracklets (55 non-player tracklets
dropped; each checked by eye) -> **13 identities** (6 red incl. orange GK,
referee, green GK, 5 green outfield). Scored with
`python -m scripts.tools.eval_identity --csv <coordinates csv> --gt data/identity_gt/match_t200_d40.csv`
(156 hand-verified `frame,x,y,label` points over 12 players, keyed by
position so it survives detector/tracker changes):

| Pipeline | stable_ids | pairwise precision | pairwise recall | GT points with no detection |
|---|---|---|---|---|
| Original (yolo11n + online rematch) | 75 | 0.960 | 0.456 | 23 / 156 |
| Current (yolo11m + offline resolution) | 13 | **1.000** | **1.000** | 0 / 156 |

Robustness (offline replay of the same evidence): with half the OCR reads
the result is unchanged; with a quarter or none, #41 can stay split
(recall 0.86) but no two different players are ever merged. Weak OCR
evidence only earns a merge bonus; vetoing a merge needs strong evidence,
because a false veto splits a player permanently.

Runtime on an RTX 4060 laptop for the 40s clip: tracking stage 455s total,
of which ReID 21s and OCR 40s (2,101 crops); resolution itself < 1s. The
rest is the yolo11m tracker, the yolo11n ball detector and annotated-video
writing.

**Known limits.**
- Green tracklets without a readable number (5 of 15) rest on ReID + motion;
  same-kit teammates are the weakest case for ReID (pairwise AUC 0.90).
- A rolling substitution would appear as extra identities; cardinality is
  only used as a lower bound, never to force a sub into another player.
- Turf HSV thresholds are tuned to this arena's turf; another venue needs
  `IDENTITY_TURF_HSV_*` checked. Kit grouping by hue fails for two kits of
  the same hue or for black/white/grey kits.
- Runtime: identity evidence roughly doubles tracking time (ReID + OCR);
  `IDENTITY_OCR_EVERY_S` / `IDENTITY_OCR_MAX_PER_TRACK` / `IDENTITY_REID_EVERY_S`
  trade accuracy for speed. `IDENTITY_RESOLVER_ENABLED = False` falls back to
  the provisional online `IdentityManager` ids.

## Goals, shots and possession on a moving camera (2026-09-23)

Uploads come from different arenas and cameras, and the camera pans and
zooms, so nothing is calibrated per venue. Every measurement is taken
relative to something visible in the same frame.

**Goals** (`scripts/vision/goals.py`). `models/goal_yolo11n.pt` (YOLO11n,
one class "goal") runs every `GOAL_DETECT_EVERY_S`. Goals don't move, so
detections from the surrounding `GOAL_SMOOTH_WINDOW_S` are carried into each
frame through the camera-motion transforms and merged; a box needs
`GOAL_MIN_SUPPORT` detections or one above `GOAL_STRONG_CONFIDENCE`.
Written to `<coordinates stem>_goals.csv`. Without the model file, shots
and goals are reported as not measured (`shots_goals_measured: false`).

*Training data* (`scripts/tools/label_goals.py`, dev-only, needs
`requirements-tools.txt`): Grounding DINO proposes boxes every 0.5 s; a
box becomes a label only if it has a goal-like size, CLIP classifies the crop
as a goal rather than a door / wall / crowd, it stands on turf, it is the
tightest box around the goal (penalty areas contain the goal and look like
one to CLIP), and the same box is found on nearby frames after camera
compensation. Every label was then reviewed by eye; the few wrong frames are
listed with `--drop-frames`. `scripts/tools/train_goal_detector.py` trains
and installs the model. Current model: 563 goal frames + 138 background
frames from the two uploads of one venue (5-min and 2-min video), val mAP50
0.995 / mAP50-95 0.86 on held-out 30 s blocks. **It has only seen one
venue**; label footage from other venues into the same dataset and retrain
before trusting it elsewhere.

**Shots and goals** (`scripts/analytics/events/shots.py`). After each
possession, the ball's flight is expressed relative to the goal box of the
same frame (pans cancel) in goal-box heights (zoom cancels):

| Outcome | Rule |
|---|---|
| goal | ball inside the goal box (inset 8%) for `GOAL_MIN_INSIDE_S`, or last seen there then gone `GOAL_VANISH_S`; not inside a player's box (keeper holding it) |
| shot | ball at the shooter's feet at the touch; struck (3-15 BH/s; faster is the ball track jumping between objects, checked per step); from within 10 GH; heading at the goal (path hits the box, or within 45 deg of the goal centre and 0.75 box widths); ends >= 0.25 GH closer; reaches 1.5 GH or is stopped by the other team |
| not a shot | ball played to a teammate; no goal in view (not measured) |

Checked by eye on the 5-min upload (no goals scored): 0 goals reported.

**Possession** (`scripts/analytics/events/possession.py`).
- Radius in the player's body heights (`POSSESSION_MAX_DISTANCE_BH`), not
  pixels, so it means the same distance at any zoom.
- The player on the ball keeps it unless a challenger is clearly closer
  (`POSSESSION_CHALLENGE_RATIO`).
- The ball must move with the player (`POSSESSION_MAX_REL_SPEED_BH_S`): on the
  5-min upload, 68% of "possessions" were 1-5 frames of a ball flying past
  someone (median relative speed ~10 BH/s vs ~1 BH/s for real possessions),
  each one splitting a pass and inventing a turnover.
- One player's spells split by up to `POSSESSION_MERGE_GAP_S` are one
  possession (a dribble).
- `PASS_MAX_TRANSITION_S` is 2 s: a 10-20 m pass takes 1-2 s. The old 0.5 s
  rejected most real passes.

**Ball filter** (`scripts/vision/ball_filter.py`). Static look-alikes are
rejected off the turf (fittings; >= 1 s) and on it (a water bottle behind the
goal line; >= 4 s, so a ball resting before a restart survives).

**Teams** (`scripts/vision/team_assigner.py`). With the identity resolver,
the two kit groups with the most detections are the teams. Anyone else is a
goalkeeper if they stay near a goal (`GOALKEEPER_*`; team = where their
distributions go), otherwise the referee (excluded from team stats).

**Known limits.**
- Interceptions are the weakest stat. A sample check still found stoppages
  (player down, card shown) and identity mix-ups (the referee merged into a
  player id) among them.
- A shot at a goal outside the view is not counted. A cut-back along the goal
  line can look like a shot in 2D.
- Goalkeepers wearing a kit close in hue to their outfield team (orange vs
  red) are grouped with that team, which is right, but the other keeper
  can share a hue with the referee (yellow).

## Analysis video (2026-09-24)

The dashboard's Tracking view plays `analysis/analysis_video*.mp4`, rendered
after match stats by `scripts/analytics/analysis_video.py`. It shows:
- a ring at each player's feet and an ID tag in the team's kit colour (the
  kit hue group from identity resolution, also written to
  `match_stats.json` `match.kit_colors` for the dashboard legend; referee
  yellow, unknown grey);
- a marker over the player on the ball;
- the ball (hollow when interpolated);
- the goal boxes;
- a clock with the possession split so far;
- captions for passes, interceptions, recoveries, shots and goals.

Frames are piped to ffmpeg (`FA_FFMPEG` or `ffmpeg` on PATH, libx264,
`+faststart`). Without ffmpeg the video is skipped and only the uploaded
footage is offered. Rendering takes ~70 s per 5 min of video.

The per-stage overlays (annotated tracking video, possession, teams, shot
validation) are written by OpenCV as MPEG-4 Part 2, which browsers can't
play, at ~0.5-0.9 GB each per 5 minutes. They are off unless
`FA_DEBUG_VIDEOS=1`, and the API never serves them.

## 30 fps analysis (2026-09-28)

Videos above `ANALYSIS_FPS` (30) are converted to 30 fps H.264 before
analysis (`scripts/pipeline/prepare_video.py`, ffmpeg with GPU decode and
encode when available; only the analysed window is converted). Tracking the
37-min 60 fps upload's 10:00-15:00 took 14.7 min instead of 37 min. Set
`FA_ANALYSIS_FPS=0` to analyse at the source frame rate.

To behave the same at any frame rate, every tracker and identity setting is
in seconds: tracker memory `TRACK_BUFFER_S`, `IDENTITY_MIN_TRACKLET_S`,
`IDENTITY_REID_EVERY_S`, `IDENTITY_OCR_EVERY_S`, the co-visibility limit in
the resolver, and minimum possession durations (rounded up so a lower frame
rate never makes them easier). At 30 fps ByteTrack gets a looser match
(`TRACK_MATCH_THRESH_30FPS`, players move twice as far per frame), and each
new track's first frame, which ByteTrack does not output, is added back from
the raw detections.

Checks:
- 40 s identity clip, same instants: 60 fps precision/recall 1.00/1.00;
  30 fps 1.00/1.00, 13 ids.
- 10:00-15:00 of the 37-min upload, 60 vs 30 fps: 0 goals both, passes
  18/18, interceptions 17/22, shots 3/4. Of the 26 events only one run
  found, checked by eye: 30 fps-only 7 real / 3 wrong / 6 unclear, 60
  fps-only 3 real / 2 wrong / 5 unclear.
- 5-min 30 fps upload re-run with these settings: 0 goals, 4 shots (the
  3 confirmed real shots kept), 28 passes, 11 interceptions, 32 ids (was
  27). The id count on long videos moves between ~25 and ~32 with small
  changes in the shirt-number evidence, so it is noisy either way.

## Cloud deployment (2026-09-28)

Vercel (site) + Render free (API) + Backblaze B2 or any S3-compatible bucket (files) + Kaggle GPU notebook (analysis). Setup steps are in `docs/DEPLOY.md`.

- `app/settings.py`: all settings from environment variables; the API never imports `config.config` (it pulls in torch, which Render's free instance can't hold).
- `app/storage.py`: x. Browser uploads go straight to storage in 64 MB multipart parts; the player gets a 307 redirect to a presigned link. Locally the links are signed `/api/files/...` routes.
- `app/jobs.py`: `FA_RUNNER=local` keeps the old in-process thread. `kaggle`/`external` queue the job; a worker claims it through `/api/worker/*` (bearer `FA_WORKER_TOKEN`), sends a heartbeat every minute and uploads results to presigned links. A job silent for `FA_WORKER_STALE_S` is requeued once, then failed. `kick()` pushes the Kaggle notebook when jobs wait and no worker has been seen, at most once per boot window.
- `app/kaggle_launcher.py`: pushes a private script notebook (GPU + internet) that clones the repo at `RENDER_GIT_COMMIT` and runs `scripts/cloud/worker.py --setup`.
- `app/pipeline_runner.py`: runs `run_mvp` and maps its output to progress; shared by the local runner and the worker.
- Checked on this machine: `tests/test_cloud_jobs.py` (start/requeue logic with a fake Kaggle), the whole upload â†’ worker â†’ results â†’ playback â†’ delete flow against local storage and against a moto S3 server standing in for the bucket, and the browser upload (CORS preflight, part PUTs, ETags) against moto. Not checked yet: a real Kaggle run (package install on Kaggle's image, T4 speed).
