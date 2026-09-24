# Football Analytics — Complete Technical Audit

**Audit date:** 2026-09-10  
**Repository:** `D:\FootballAnalytics`  
**Method:** Source inspection. Claims in comments/README that conflict with code are called out.  
**Code was not modified.**

If something could not be confirmed from code or a live version query, it is marked **NOT VERIFIED**.

---

## Phase 1 — Repository inventory

### Layout (project source; excludes `frontend/node_modules` and `__pycache__`)

| Area | Path | Status |
|---|---|---|
| Product API | `app/main.py`, `app/jobs.py`, `app/store.py`, `app/auth.py` | IMPLEMENTED |
| Pipeline entry | `scripts/pipeline/run_mvp.py` | IMPLEMENTED |
| Tracking / CV | `scripts/track.py` | IMPLEMENTED |
| Identity | `scripts/identity/identity_manager.py`, `player_profile.py` | IMPLEMENTED |
| Coordinates | `scripts/coordinate_logger.py` | IMPLEMENTED |
| Possession | `scripts/analytics/events/possession.py` | IMPLEMENTED |
| Passes | `scripts/analytics/events/passes.py` | IMPLEMENTED |
| Turnovers | `scripts/analytics/events/turnovers.py` | IMPLEMENTED |
| Shots | `scripts/analytics/events/shots.py` | IMPLEMENTED |
| Match stats | `scripts/analytics/match_stats.py` | IMPLEMENTED |
| Teams | `scripts/vision/team_assigner.py`, `jersey_color.py` | IMPLEMENTED |
| Motion/heatmaps | `scripts/analytics/motion_engine.py`, `heatmap.py`, `distance.py`, `speed.py`, `trajectory.py`, `smoothing.py`, `draw_trajectory.py` | IMPLEMENTED (pixel analytics; used by `run_mvp`) |
| Pitch mapper | `scripts/analytics/pitch_mapper.py` | IMPLEMENTED but **UNUSED** by event/stats path |
| Pitch metres | `data/pitch/pitch_dimensions.py` | UNUSED by events |
| ROI tools | `scripts/tools/select_roi.py`, `validate_roi.py`, `data/roi/camera_001.json` | IMPLEMENTED as tools; **not** used by shots |
| Standalone detect | `scripts/detect.py` | UNUSED by product pipeline (older detect-only script) |
| Model download | `scripts/download_model.py` | IMPLEMENTED utility |
| Identity audit CLI | `scripts/tools/audit_identity.py` | IMPLEMENTED |
| Ad-hoc tests | `scripts/test.py`, `test_*.py` | EXPERIMENTAL / manual scripts (no pytest suite found) |
| Config | `config/config.py`, `config/bytetrack.yaml` | IMPLEMENTED |
| Frontend | `frontend/src/**` | IMPLEMENTED (Vite + React) |
| Models | `models/yolo11n.pt` | IMPLEMENTED (YOLO11n COCO) |
| Videos | `videos/raw/`, `videos/test/` | Local assets; gitignored `*.mp4` |
| Outputs | `outputs/` | Generated; gitignored |
| Product data | `data/uploads/`, `data/matches_index.json`, `data/users.json` | Runtime; gitignored except ROI |
| API extras | `requirements-api.txt` | FastAPI/uvicorn/multipart only |
| Root `requirements.txt` | — | **NOT PRESENT** |
| Root README | — | **NOT PRESENT** (frontend README is from node_modules only) |
| Scapy | — | **NOT FOUND** |
| FFmpeg CLI | — | **NOT FOUND** (OpenCV `VideoWriter` used instead) |
| Chart library | — | **NOT FOUND** |

### Important files

**FILE:** `config/config.py`  
**PURPOSE:** Hardcoded `PROJECT_ROOT = D:\FootballAnalytics`; model/video/output paths; event thresholds; CUDA vs CPU. Side effect: creates output folders and prints `Configuration Loaded Successfully!` on import.  
**INPUTS:** `FA_OUTPUT_DIR` env (optional), `torch.cuda.is_available()`.  
**OUTPUTS:** Path constants, `DEVICE`, `DEVICE_LABEL`.  
**DEPENDENCIES:** `torch`, `pathlib`, `os`.  
**CALLED BY:** Nearly all Python modules.  
**CALLS:** Folder `mkdir`.  
**STATUS:** IMPLEMENTED. Limitation: Windows-absolute root.

**FILE:** `scripts/pipeline/run_mvp.py`  
**PURPOSE:** End-to-end CLI: track if needed → motion/heatmaps → possession → teams → passes → turnovers → shots → match stats.  
**INPUTS:** `--video`, `--csv`, `--force-track`, `--max-frames`, `--start-time`, `--duration`, skip flags. Default video: `TEST_VIDEO`.  
**OUTPUTS:** Segment-tagged CSVs/JSON under `OUTPUT_DIR` (`FA_OUTPUT_DIR` if set).  
**STATUS:** IMPLEMENTED.

**FILE:** `scripts/track.py` — `run_tracking`  
**PURPOSE:** YOLO person `track` + separate ball `predict`; IdentityManager; CoordinateLogger; annotated MP4.  
**STATUS:** IMPLEMENTED.

**FILE:** `app/main.py`  
**PURPOSE:** FastAPI product API.  
**STATUS:** IMPLEMENTED.

**FILE:** `frontend/src/App.tsx`  
**PURPOSE:** Routes + auth wrapper.  
**STATUS:** IMPLEMENTED.

Ad-hoc `scripts/test_*.py` are one-off checks (config, heatmap, identity, jersey, pitch mapper, etc.). They are not a CI test suite. **STATUS:** EXPERIMENTAL.

---

## Phase 2 — Architecture reconstruction

See also `docs/ARCHITECTURE.md`.

**Actual product path:** browser → FastAPI → filesystem JSON index → one-thread job queue → subprocess `python -m scripts.pipeline.run_mvp` with `FA_OUTPUT_DIR=outputs/matches/{match_id}` → engines write CSVs → `match_stats*.json` copied to `match_stats.json` with display names injected → dashboard `GET /api/matches/{id}/stats`.

**CLI path (disconnected from UI unless you copy JSON):** `python -m scripts.pipeline.run_mvp --video ...`

Homography, metres, live dashboard video player, `events[]` timeline payload: **NOT IMPLEMENTED** in the product data layer (timeline UI exists but empty by design).

---

## Phase 3 — Computer vision pipeline

### Player detection

| Item | Value |
|---|---|
| Model file | `models/yolo11n.pt` |
| Type | Ultralytics YOLO11n, COCO pretrained (download helper: `scripts/download_model.py`) |
| Inference | `YOLO.track` in `scripts/track.py` |
| Classes used | `person` only (`cls_name != "person"` skipped) |
| `imgsz` | 1280 |
| `conf` | 0.30 |
| Device | `config.DEVICE`: CUDA `0` if available else `"cpu"` (verified this machine: CUDA True, torch `2.6.0+cu124`) |
| Boxes without `box.id` | skipped (no track ID → no log) |
| Position for identity | bbox bottom-centre `((x1+x2)/2, y2)` |

### Ball detection (separate from tracking)

Why separate (code comments + implementation): a second `YOLO` instance is loaded as `ball_model`. Using `predict` on the **same** instance as `track` would reset Ultralytics ByteTrack state.

| Item | Value |
|---|---|
| Same weights | `yolo11n.pt` |
| Method | `ball_model.predict` |
| Class | COCO `32` / name `sports ball` |
| `conf` | `BALL_CONFIDENCE = 0.10` |
| `imgsz` | `BALL_IMGSZ = 1280` |
| ByteTrack | **No** |
| IdentityManager | **No** |
| `track_id` / `stable_id` | empty in CSV |
| Multi-candidate | highest confidence kept; count of multi-candidate frames logged |
| Interpolation | **Not in tracker.** Linear interp later in `PossessionEngine._ball_series` for gaps ≤ 15 frames |
| Missing frames | no ball row in CSV; possession state `unknown` |

`possession.py` module docstring mentions “separate IdentityManagers” for ball. **Code contradiction:** `track.py` does not give the ball an IdentityManager. Trust `track.py`.

### Player tracking (ByteTrack)

File: `config/bytetrack.yaml`

```
tracker_type: bytetrack
track_high_thresh: 0.5
track_low_thresh: 0.1
new_track_thresh: 0.6
track_buffer: 30
match_thresh: 0.8
fuse_score: True
```

Called as `model.track(..., tracker=str(TRACKER_CONFIG), persist=True, ...)`.

**Lifecycle:** Ultralytics assigns `box.id`. New IDs appear after occlusions/exits beyond ByteTrack buffer. IdentityManager may remap a **new** `track_id` onto an existing `stable_id`.

**Limitations:** indoor clutter, overlapping players, `track_buffer: 30` frames (~0.5 s at 60 fps) is short vs identity rematch gap of 150 frames. Fragmentation is expected.

### Stable identity

| Concept | Meaning in this repo |
|---|---|
| `track_id` | ByteTrack ID for the current fragment |
| `stable_id` | Integer assigned by `IdentityManager`; **MVP identity, not a unique real player** |

`IdentityManager.get_stable_id` (`scripts/identity/identity_manager.py`):

1. If `track_id` already mapped → update profile, return same `stable_id`.
2. Else `find_matching_player`:
   - Skip candidates with `frame_gap > 150`.
   - Skip if candidate’s `stable_id` is in `active_tracks.values()` (`candidate_active`).
   - Skip if Euclidean distance of **feet position** ≥ `120` px.
   - If **both** current crop colour and stored jersey BGR exist and Euclidean BGR distance > `80` → reject (`appearance_incompatible`). Missing colour does **not** reject.
   - Accept nearest remaining candidate.
3. Else `register_new_player` (increment `next_stable_id`).

Jersey colour on profiles is a running average of upper-body mean BGR (`JerseyColorExtractor`).

**Fragmentation:** new `stable_id` whenever rematch fails (gap, distance, active collision, appearance). 40s clip historically produced ~75 identity-audit IDs vs ~10–16 visible people (`data_quality.estimated_visible_players` is a **hardcoded string** `"~10-16"` in `match_stats.py`, not a measurement).

Audit CSVs: `outputs/identity/rematch_audit.csv` when enabled.

---

## Phase 4 — Jersey / team assignment

**TEAM IDENTIFICATION** ≠ **PLAYER IDENTIFICATION.** Colour clustering assigns `team_a` / `team_b` / `referee` / `unknown` to each `stable_id`. It does not uniquely identify a person.

### JerseyColorExtractor (`scripts/vision/jersey_color.py`)

- Crop bbox, clamp to frame.
- Take top `upper_body_ratio=0.40` of crop.
- Mean BGR of that region (no clustering inside the crop).
- Helpers: `bgr_to_hsv`, `bgr_to_lab` (Lab **reserved**, not used for clustering).

### Team assignment (`scripts/vision/team_assigner.py`)

- Sample person rows with `confidence >= 0.45`, stride 5, max 40 samples per `stable_id`.
- Representative colour: robust median-style helper `_robust_representative`.
- Feature: HSV as `(cos(h)*sat, sin(h)*sat, val)`.
- `cv2.kmeans` k=2 if ≥4 clusterable IDs; else all `unknown`.
- Cluster → `team_a`/`team_b` by mean hue order.
- Referee: yellow-like HSV (`18–40`, S/V ≥ 80) and far from centres (`TEAM_REFEREE_MIN_CENTROID_DIST = 0.45`).
- Ambiguous if ratio > `0.88` or confidence < `0.35`.

Outputs: `outputs/teams/player_teams.csv` (or segment-tagged), `team_swatches.png`, optional `team_validation.mp4`.

**Limitations:** pitch/green contamination in crops; fragmented IDs get independent samples; k=2 assumes two kits.

---

## Phase 5 — Possession engine

File: `scripts/analytics/events/possession.py` — class `PossessionEngine`.

| Parameter | Config |
|---|---|
| Interpolation gap | `MAX_BALL_INTERPOLATION_GAP = 15` frames |
| Possession radius | `MAX_POSSESSION_DISTANCE_PX = 150` (ball bbox-centre vs player **feet** CSV centre) |
| Confirm | `POSSESSION_CONFIRM_FRAMES = 5` |

Ball XY for possession: **bbox centre** `(x1+x2)/2, (y1+y2)/2` from ball rows, not player feet convention.

**Interpolation:** between two detections if gap in `(0, 15]`; linear x/y/confidence; `source=interpolated`. Larger gaps stay `missing`.

**Per-frame logic:**

- No ball → `possession_state=unknown`, `possessor=None`, pending reset.
- Ball present: nearest person within 150 px is `target`, else `target=None`.
- Same `target` must hold for 5 consecutive frames to become `confirmed`.
- 5 consecutive `target=None` → `confirmed=None`, state `loose`.
- Meanwhile: `candidate` if pending player (possessor still last confirmed); `loose` if pending none but not yet 5 frames (possessor still last confirmed).

**Ownership change:** confirmed ID changes after 5-frame confirmation of a new target.

**Possession time (match_stats):** confirmed interval frame count × `(1/fps)`. Team % = share of team_a+team_b confirmed seconds (sums to 100%); loose/unknown excluded from the split. If no team possession seconds, percentages are **null**.

Output: `frame_state.csv` (or `frame_state_t{start}_d{dur}.csv`).

---

## Phase 6 — Event analytics

All events are **post-process** on confirmed possession intervals + teams. Conservative: miss rather than invent.

### Pass (`passes.py` — `classify_transition`)

Inputs: consecutive confirmed intervals, teams, ball stats on the open interval.

Completed pass if:

- different `stable_id`
- both possessions ≥ 5 frames
- gap ≤ 30 frames
- missing-ball ratio in gap ≤ 0.50 (if gap has frames)
- both teams in `{team_a, team_b}`
- **same team**

Rejected: same id, too short, gap too long, ball too missing.

Unknown transition: invalid/missing team, or **cross-team** (passes do not steal interceptions).

`pass_accuracy` is **always null** (no attempted-pass definition).

40s demo (prior run, not re-measured this audit): 2 completed passes. **NOT RE-VERIFIED this session.**

### Interception (`turnovers.py`)

After skipping pairs that `classify_transition` already called `completed_pass`:

- Cross-team, both valid, both possessions ≥ 5, gap ≤ 30, ball missing ratio ≤ 0.50 → **interception**.

Cross-team is **not** automatic: long gap → `unknown_turnover`; missing ball → rejected; same-id / short possession → rejected.

### Ball recovery

If not pass-domain and not interception: valid new owner, gap ≤ 30, mostly loose/unknown in the gap (`loose_ratio >= 0.5` or empty gap), and not both-valid same-team leftover → **recovery**.

### Shot / on target / goal (`shots.py`)

Pixel goal boxes (`config.py`):

- Left: `(150, 165, 370, 760)`
- Right: `(1570, 180, 1910, 860)`
- `TEAM_DEFENDS_GOAL`: team_a left, team_b right → shooter attacks the **other** box.

Algorithm (`classify_shot_interval`): after a confirmed possession (≥5 frames), look at ball trajectory up to 90 frames (capped by next interval / clip). Reject if next interval looks like a same-team pass (gap ≤ 30). Require movement ≥ 80 px, toward opponent box, approach ≥ 25 px closer, not already inside, confidence HIGH or MEDIUM (LOW rejected).

**On target** if: entered zone from outside, **or** trajectory segment intersects box, **or** min distance to box ≤ 45 px while toward+approaches.

**Goal** only if on-target **and** `entered_from_outside` **and** consecutive inside-run ≥ `SHOT_GOAL_INSIDE_FRAMES = 2`. Comment/code: no goal from missing-ball-only evidence.

Validation video optional (`SHOT_WRITE_VALIDATION_VIDEO = True`).

### Not implemented (not found as engines)

Tackles, fouls, offsides, assists, key passes, xG, expected threat, set-piece classification, player names/numbers OCR, live broadcast feed ingest.

---

## Phase 7 — Pitch / goal geometry

| Asset | Used by events? |
|---|---|
| `data/roi/camera_001.json` pitch quad | No (ROI validation tools only) |
| `GOAL_ZONE_*` pixel boxes | **Yes** (shots) |
| `PitchMapper` 1920×1080 → `assets/pitch.png` | No |
| `pitch_dimensions.py` 40×20 m | No |
| Homography | **NOT IMPLEMENTED** |

Events operate in **image/pixel coordinates**. No real-world metres in possession/passes/shots.

---

## Phase 8 — Match statistics data layer

`scripts/analytics/match_stats.py` — `build_match_stats` → JSON `pipeline_version: mvp-product-data-v1`.

Also writes a debug CSV of team/player rows.

### JSON (main keys)

`match`, `generated_at`, `pipeline_version`, `identity_quality` (`MVP_FRAGMENTED`), `data_quality`, `event_summary`, `teams.team_a|team_b`, `players[]`, `known_limitations[]`, `inconsistencies[]`, `validation`.

**No `events[]` array** — dashboard timeline stays empty.

### 0 vs null

| Field | 0 | null |
|---|---|---|
| goals, shots, SOT, completed_passes, intercepts, recoveries, player possession seconds | true zeros when none attributed | — |
| `pass_accuracy` (team and player) | never 0 | **always null** |
| `shot_accuracy`, `shot_conversion_rate` | never 0 when shots=0 | **null if shots=0**; percent if shots>0 |
| `possession_percentage` | 0.0 from `_empty_team` only before fill | **null** if no confirmed team possession seconds |

`_ratio_or_null(num, den)` returns null when denominator is 0.

Validation checks team sums vs player sums vs event_summary; possession % sum 100; pass_accuracy always null.

---

## Phase 9 — Backend / API

**Framework:** FastAPI (`app/main.py`), uvicorn.  
**Jobs:** `app/jobs.py` — one daemon thread, `queue.Queue`, subprocess pipeline.  
**Store:** `data/matches_index.json` (not SQL).  
**Uploads:** `data/uploads/{uuid}/video{ext}`, max 8 GB, extensions `.mp4 .mov .avi .mkv`.  
**Outputs:** `outputs/matches/{match_id}/`.

CORS: localhost/127.0.0.1 ports 5173 and 5174.

### Endpoints that exist

**METHOD:** GET **PATH:** `/api/health`  
**PURPOSE:** Liveness. **REQUEST:** none. **RESPONSE:** `{"ok": true}`. **AUTH:** none.

**METHOD:** POST **PATH:** `/api/auth/signup`  
**REQUEST:** `{email, password, name?}`. **RESPONSE:** `{user, token}`. **ERRORS:** 400 invalid/duplicate. **SIDE:** writes `data/users.json`.

**METHOD:** POST **PATH:** `/api/auth/login`  
**ERRORS:** 401.

**METHOD:** GET **PATH:** `/api/auth/me`  
**AUTH:** Bearer. **ERRORS:** 401.

**METHOD:** POST **PATH:** `/api/matches/upload`  
**AUTH:** Bearer. **REQUEST:** multipart file. **RESPONSE:** `{match_id, filename, status, bytes, created_at}`. **SIDE:** file + index row `status=uploaded`. **ERRORS:** 400 empty/bad type, 413 too large, 401.

**METHOD:** GET **PATH:** `/api/matches`  
**RESPONSE:** `{matches: [...]}` filtered by `user_id`. `list_matches` includes rows whose `user_id` is the current user, `None`, or `""` (legacy/shared rows).

**METHOD:** GET **PATH:** `/api/matches/{match_id}`  
**ERRORS:** 400 bad UUID, 404, 403.

**METHOD:** DELETE **PATH:** `/api/matches/{match_id}`  
**ERRORS:** 409 if queued/processing. **SIDE:** deletes match files via `delete_match`.

**METHOD:** POST **PATH:** `/api/matches/{match_id}/analyze`  
**BODY:** `{team_a, team_b, camera, analysis: full|window, start_time_s, duration_s}`.  
**SIDE:** enqueue job. **ERRORS:** 409 already running, 400 window without duration.

**METHOD:** GET **PATH:** `/api/matches/{match_id}/status`  
Progress is **stage-based** from stdout needles, not percent of frames.

**METHOD:** GET **PATH:** `/api/matches/{match_id}/stats`  
**ERRORS:** 409 if not `completed`, 404 missing JSON.

**METHOD:** GET **PATH:** `/api/matches/{match_id}/video`  
FileResponse source video. **HEAD not defined** (405 if clients probe HEAD).

**METHOD:** GET **PATH:** `/api/matches/{match_id}/analysis-video`  
First existing of `team_validation.mp4`, `possession_validation.mp4`, then glob `*validation*.mp4`.

There is no REST “create match without upload” besides upload.

---

## Phase 10 — Frontend

| Item | Value |
|---|---|
| Framework | React 19 |
| Language | TypeScript |
| Router | react-router-dom 7 |
| Build | Vite 7 |
| Charts | none |
| State | React `useState`/`useContext` (`AuthContext`); no Redux |
| API | `fetch` via `frontend/src/api/client.ts` (Bearer `localStorage` key `fa_token`); Vite proxy `/api` → `127.0.0.1:8000` |

**Routes:** `/` home, `/login`, `/signup`, `/upload`, `/matches`, `/matches/:id`, `/matches/:id/setup`, `/matches/:id/processing`. Unknown → `/`.

**User journey that exists:** Landing → login/signup → upload (local preview `<video>`) → setup (names + full vs window) → processing (polls status) → dashboard (scoreboard, team comparison, player table, event **counts**, empty timeline, data-quality).

Dashboard does **not** embed match or analysis video (API exists).

---

## Phase 11 — End-to-end data flow (upload)

1. User picks file — `UploadPage.tsx`.
2. `POST /api/matches/upload` — `upload_match` in `app/main.py`.
3. Bytes to `data/uploads/{uuid}/video.ext`; row in `matches_index.json`.
4. Setup `POST .../analyze` — `enqueue` in `app/jobs.py`.
5. Worker `_run_job` subprocess `scripts.pipeline.run_mvp --video ... --force-track` [`--start-time/--duration`], `FA_OUTPUT_DIR`.
6. `run_tracking`: person `YOLO.track` + ball `predict`.
7. CSV `CoordinateLogger`.
8. `MotionEngine` + `HeatmapEngine` (pixel heatmaps).
9. `run_possession` → frame_state.
10. `run_team_assignment`.
11. `run_pass_detection`, `run_turnover_detection`, `run_shot_detection`.
12. `run_match_stats` → `analytics/match_stats*.json`.
13. `_finalize_stats` copies to `match_stats.json`, injects team names.
14. `GET /api/matches/{id}/stats` — `DashboardPage` `getMatchStats`.

**Manual/disconnected:** CLI without API; PitchMapper tests; `detect.py`; ROI tools; copying a precomputed 40s match into the index (demo match ID may exist in local `matches_index.json`, gitignored).

---

## Phase 12 — Performance / hardware

Verified on audit machine:

- Python **3.10.11**
- torch **2.6.0+cu124**, CUDA **True**
- opencv-python reported **5.0.0**
- pandas **2.2.3**, numpy **2.2.6**
- ultralytics **8.4.104**

Node/npm: **NOT VERIFIED** (shell spawn failed this session).

YOLO: YOLO11n file `yolo11n.pt`. GPU used when CUDA available; else CPU.

Video: ROI/config comments assume **1920×1080**. FPS read from file (demo ~59.94). Do not hardcode 60.

Processing speed: **no benchmark numbers in repo**. Full-match runtime **NOT VERIFIED**. Dual YOLO (track + predict) per frame is inherently expensive.

`MAX_FRAMES` env in `track.py` can cap standalone tracking.

---

## Phase 13 — Capabilities

### WORKING (demonstrable)

- Auth signup/login, upload, setup, queued analysis, status polling, dashboard JSON.
- Person detect+track, ball detect, CSV, heatmaps, possession frame_state, jersey teams, conservative pass/turnover/shot labels, match_stats JSON.
- CLI windowed runs (`--start-time/--duration`).

### PARTIALLY WORKING / MVP

- Identity (fragmented).
- Team assignment (colour, pitch contamination).
- Events (undercount by design).
- Shots/goals (manual pixel boxes; right goal poorly framed per config comments).
- Possession % (share of confirmed team time, not clock time).
- Analysis-video endpoint without UI player.
- Event timeline UI without `events[]`.
- Legacy matches with empty `user_id`.

### NOT IMPLEMENTED

- Homography / metric pitch.
- Unique real-player ID / jersey number OCR.
- Pass accuracy, xG, tackles, assists.
- Multi-camera, PTZ, broadcast tracking.
- Production auth, multi-worker scale, object store.
- Automated pytest CI.
- Charting.
- Root README / unified requirements.txt.

---

## Phase 14 — Limitations (ranked)

| Rank | Limitation | Impact |
|---|---|---|
| CRITICAL | `stable_id` fragmentation | Player table splits one person across many rows; stats not career-true |
| CRITICAL | Hardcoded `PROJECT_ROOT` | Breaks on other machines/paths unless that exact drive layout exists |
| HIGH | Dual per-frame YOLO | Slow; full 37-min match painful |
| HIGH | Conservative events | Passes/shots/goals undercounted vs human tally |
| HIGH | Manual goal geometry | Wrong camera crop → wrong SOT/goals |
| HIGH | No metres/homography | Distances are pixels; not comparable across cameras |
| HIGH | Local JSON auth | Not production security |
| HIGH | Single analysis worker | Jobs serialize; no cancel of in-flight subprocess documented |
| MEDIUM | Team colour uncertainty | Wrong team → wrong pass vs intercept |
| MEDIUM | Ball COCO detect at 0.10 | False balls / misses; indoor lighting |
| MEDIUM | ByteTrack buffer 30 vs rematch 150 | Identity layer fights tracker churn |
| MEDIUM | Possession % ≠ clock share | Users may misread “64% possession” |
| MEDIUM | `pass_accuracy` always null | Dashboard must show N/A not 0% |
| MEDIUM | One-job / no HEAD on video | Players/proxies may fail |
| LOW | `estimated_visible_players` hardcoded | Data-quality UI can mislead |
| LOW | PitchMapper unused | Dead-end for “tactical pitch view” |
| LOW | `detect.py` unused / device hardcoded | Confusion for new contributors |

---

## Phase 15 — Security / reliability (document only)

- Filename sanitized (`_safe_filename`) and stored as `video{ext}` under UUID dir — path traversal of original name largely mitigated.
- Match IDs UUID-regex validated.
- 8 GB cap after streaming write; large files still DoS disk.
- Auth: PBKDF2 120k, HMAC tokens 14-day TTL, secret file gitignored; tokens in `localStorage`; no refresh rotation.
- CORS limited to local Vite ports.
- Concurrent analyze: 409 per match; **global queue is single-threaded** — other matches wait.
- Failed jobs: `error.log` last 400 stdout lines; user message generic.
- Stale outputs: `--force-track` on product jobs always re-tracks.
- `os.link` for video copy may fail on Windows; ignored.
- `config.py` import creates directories (surprise I/O).
- Users JSON is plaintext emails + password hashes on disk.
- No virus scan of uploads.
- `list_matches` empty `user_id` visibility: check `app/store.py` when changing auth.

---

## Phase 16 — Tech stack (found)

### Frontend
React 19, TypeScript, react-router-dom 7, Vite 7, CSS (`index.css`). No chart lib.

### Backend
Python 3.10, FastAPI, uvicorn, python-multipart, Pydantic models in `main.py`.

### Computer vision
Ultralytics YOLO11n, ByteTrack yaml, OpenCV (VideoCapture/Writer, kmeans, colour). **Not** Scapy. **Not** FFmpeg CLI.

### ML
PyTorch 2.6+cu124 (this machine). Pretrained COCO YOLO11n — **not** a custom-trained detector in-repo.

### Analytics
Python, pandas, numpy. Heuristic event engines.

### Infrastructure
Local filesystem, subprocess, one background thread. No Docker/K8s found.

---

## Phase 17 — Engineering value (actual vs future)

**Actual:** video→CSV pipeline; split ball predict vs person track; ByteTrack + rematch identity; jersey team clustering; explainable post-process events; unified JSON with explicit nulls and limitations; product wrap (upload/jobs/dashboard).

**Not actual:** real-time inference SLA, broadcast accuracy, metric pitch, unique player ID, xG.

---

## Phase 21 — Roadmap (current vs future)

### V1 — Current MVP
Pipeline + JSON + local web app as documented.

### V1.1 — Reliability (future)
Portable `PROJECT_ROOT`; identity fragmentation; job cancel; video player; `events[]`; requirements freeze; tests.

### V2 — Better analytics (future)
Homography or calibrated goals; less conservative but validated events; pass attempts; better ball association.

### V3 — Product (future)
Multi-user DB, queue workers, GPU service, jersey OCR, multi-cam — **none exist now**.

---

## Phase 23 — Command reference (repo-backed)

Install API extras:

```
pip install -r requirements-api.txt
```

CV stack: **no root requirements.txt**. Packages used include `ultralytics`, `torch`, `opencv-python`/`cv2`, `pandas`, `numpy`. Exact pin file: **NOT PRESENT**.

Download weights if missing:

```
python scripts/download_model.py
```

Backend:

```
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend:

```
cd frontend
npm install
npm run dev
```

Build frontend:

```
cd frontend
npm run build
```

Pipeline (example 40s window on raw match — requires local `videos/raw/match.mp4`):

```
python -m scripts.pipeline.run_mvp --video videos/raw/match.mp4 --start-time 200 --duration 40 --force-track
```

Default CLI video is `videos/test/match_test.mp4` (~120s). Start 200s on the **test** file will fail (too short) — code raises.

Isolated outputs:

```
set FA_OUTPUT_DIR=D:\FootballAnalytics\outputs\matches\demo
python -m scripts.pipeline.run_mvp --video ... --force-track
```

Tests: no pytest entry. Manual scripts e.g. `python scripts/test_config.py`.

Inspect outputs: `outputs/coordinates/`, `outputs/events/`, `outputs/analytics/match_stats*.json`, or `outputs/matches/{id}/`.

CUDA check: `python scripts/test.py`.

---

## Phase 24 — Executive summary

**PROJECT:** FootballAnalytics — indoor fixed-camera match analytics MVP.  
**GOAL:** Turn a video into conservative possession/event stats and a local dashboard.  
**CURRENT STATUS:** Working local product + CLI; identity and events are MVP-quality.  
**TECH STACK:** YOLO11n, ByteTrack, OpenCV, pandas, FastAPI, React/Vite.  
**MAIN PIPELINE:** detect/track → CSV → possession → teams → events → JSON → API → UI.  
**KEY FEATURES:** Split ball detector, stable_id rematch, jersey teams, heuristic events, match_stats schema.  
**BIGGEST TECHNICAL ACHIEVEMENT:** Modular post-process analytics on tracked CSV without claiming broadcast stats.  
**BIGGEST LIMITATION:** Fragmented identities + pixel-only geometry + conservative undercount.  
**CURRENT MVP QUALITY:** Demo-able on short clips; not production sports data.  
**NEXT BEST IMPROVEMENT:** Portable config + identity robustness (then calibrated goals).

---

## Audit coverage note

Inspected: `app/` (5 py), `scripts/` (43 py), `config/`, `frontend/src` (~20 source files), `data/roi`, requirements-api, gitignore, bytetrack yaml, shots/passes/turnovers/possession/match_stats/track/identity/jersey/team_assigner/jobs/main.  
Did not treat `node_modules` as project source.  
Did not re-run the 40s pipeline this session.
