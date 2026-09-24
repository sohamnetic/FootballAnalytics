# FOOTBALL ANALYTICS PROJECT — AI HANDOFF CONTEXT

Paste this at the start of a new Claude/GPT/Cursor session. **Trust this + the code.** Do not invent features. Do not “fix” event engines unless the user explicitly asks.

**Audit date:** 2026-09-10. Source of truth: repository, not marketing copy.

---

## 1. Project goal

Local MVP: indoor football video from a **panning** broadcast-style camera → detections/tracks → CSV → possession/teams/events → `match_stats.json` → FastAPI → React dashboard. Prefer **missing events over false positives**. `stable_id` is an offline-resolved player identity (validated on the 40s clip), still an estimate.

## 2. Current architecture

```
Browser (Vite :5173, proxy /api)
  → FastAPI (uvicorn :8000)
      uploads + matches_index.json + users.json
      1 worker thread → subprocess run_mvp (FA_OUTPUT_DIR=outputs/matches/{id})
          YOLO11m track persons + ByteTrack (buffer 90)
          YOLO11n predict sports ball (class 32, no tracker)
          IdentityManager (provisional) + TrackletFeatureCollector
          resolve_identities (rewrites stable_id, drops non-players)
          CoordinateLogger CSV
          MotionEngine + heatmaps
          PossessionEngine
          team_assigner
          passes / turnovers / shots
          match_stats.json
  → Dashboard GET /api/matches/{id}/stats
```

CLI can run the same engines without the UI.

## 3. Repository structure

```
app/                    FastAPI (main, jobs, store, auth)
config/                 config.py, bytetrack.yaml
scripts/track.py        CV loop
scripts/pipeline/run_mvp.py   CLI orchestrator
scripts/identity/       IdentityManager (provisional), tracklet_features, resolver (final ids)
scripts/vision/         jersey_color, team_assigner
scripts/analytics/      motion, heatmap, match_stats
scripts/analytics/events/  possession, passes, turnovers, shots
scripts/coordinate_logger.py
scripts/detect.py       UNUSED by product
scripts/tools/          ROI, identity audit
frontend/src/           React product UI
models/yolo11n.pt (ball), yolo11m.pt (persons), lmbn_n_duke.pt (ReID) — scripts/download_model.py
data/roi/               pitch quad JSON (not goal posts)
data/uploads/           runtime
outputs/                CLI + per-match product dirs
docs/                   this audit set
```

No root `requirements.txt` or README. `requirements-api.txt` is FastAPI only.

## 4. Tech stack

Python 3.10, Ultralytics YOLO11m/11n, ByteTrack, boxmot LMBN ReID, EasyOCR, OpenCV, pandas/numpy, PyTorch (CUDA if available), FastAPI/uvicorn, React 19 + Vite 7 + react-router 7. No Scapy, no FFmpeg CLI, no chart library, no pytest suite.

## 5. Important files

| File | Role |
|---|---|
| `config/config.py` | Thresholds; **hardcoded** `PROJECT_ROOT = D:\FootballAnalytics`; `FA_OUTPUT_DIR` override |
| `scripts/track.py` | `run_tracking` |
| `scripts/identity/resolver.py` | `resolve_identities` (final ids) |
| `scripts/identity/tracklet_features.py` | per-detection identity evidence |
| `scripts/analytics/events/*.py` | Possession/events |
| `scripts/analytics/match_stats.py` | Product JSON |
| `app/main.py` `app/jobs.py` | API + subprocess |
| `frontend/src/pages/*` | UX |

## 6. Pipeline flow

`run_mvp`: if CSV missing or `--force-track` → `run_tracking` → analytics CSV/heatmaps → `run_possession` → `run_team_assignment` → `run_pass_detection` → `run_turnover_detection` → `run_shot_detection` → `run_match_stats`. Segment suffix `t{start}_d{duration}` on outputs when windowed.

Product jobs always `--force-track`.

## 7. Current data formats

Coordinate CSV columns: `frame, track_id, stable_id, class, confidence, x1,y1,x2,y2, center_x, center_y`.  
Person centre = feet (bottom-centre). Ball centre = bbox centre. Ball track/stable empty.

`frame_state.csv`: ball xy, source detected/interpolated/missing, nearest player, possessor, state confirmed|candidate|loose|unknown. `time_s = (frame-1)/fps`.

Teams CSV: `stable_id, team_id, sample_count, representative_color, confidence, reason`.

`match_stats.json`: teams, players, event_summary, data_quality, known_limitations, validation. **No `events[]`.** `pass_accuracy` always `null`. Shot rates `null` if shots=0. Possession % = share of confirmed team_a+team_b seconds, sums to 100, else null.

## 8. Current APIs

`GET /api/health`  
`POST /api/auth/signup|login` `GET /api/auth/me`  
`POST /api/matches/upload`  
`GET /api/matches` `GET|DELETE /api/matches/{id}`  
`POST /api/matches/{id}/analyze` body `{team_a,team_b,camera,analysis:full|window,start_time_s,duration_s}`  
`GET .../status|stats|video|analysis-video`  

Auth: `Authorization: Bearer`. Match IDs UUID. Upload ≤8GB, ext mp4/mov/avi/mkv. CORS 5173/5174. HEAD `/video` not defined (405).

`list_matches`: rows with `user_id` in `{current, None, ""}` are visible.

## 9. Current frontend

Routes: `/` `/login` `/signup` `/upload` `/matches` `/matches/:id` `/setup` `/processing`.  
Token: `localStorage fa_token`.  
Dashboard: scoreboard, team comparison, player table, event **counts**, empty timeline, data-quality. No in-dashboard video player. No charts.

## 10. Implemented features

Player detect/track, ball detect, identity rematch, heatmaps, possession, jersey teams (a/b/referee/unknown), completed passes, conservative intercepts/recoveries, shots/SOT/goals (against goals detected in the video, `models/goal_yolo11n.pt`), match stats JSON, local upload product, windowed analysis.

## 11. Known limitations

- Identity (2026-09-23): offline resolution (ReID + jersey OCR + pan-compensated
  motion + hard constraints, `scripts/identity/resolver.py`). 40s clip: 75 ids
  -> 13; pairwise precision/recall 0.96/0.46 -> 1.00/1.00 on 156 hand-verified
  points (`data/identity_gt/match_t200_d40.csv`, scored by
  `python -m scripts.tools.eval_identity`). Only validated on this clip/venue.
- Dual YOLO/frame → slow full matches.  
- No homography/metres on the event path; distances are in player body heights / goal-box heights (zoom-independent).  
- Goals are detected (2026-09-23; the fixed `GOAL_ZONE_*` pixel boxes are gone). The goal model has only seen **one venue**; retrain with `scripts/tools/label_goals.py` + `train_goal_detector.py` on footage from other venues. Rules: docs/architecture.md *Goals, shots and possession on a moving camera*.  
- Interceptions are the weakest stat (stoppages, identity mix-ups such as the referee merged into a player id).  
- Conservative undercount of events.  
- Team colour / pitch contamination.  
- Hardcoded Windows `PROJECT_ROOT`.  
- Local JSON auth; one analysis worker.  
- `estimated_visible_players` hardcoded `"~10-16"`.  
- PitchMapper unused by events.  
- `possession.py` docstring mentioning ball IdentityManager is **stale**; ball has none.

## 12. Architectural decisions

Two YOLO instances; ball not ByteTracked; events post-CSV; possession % not clock share; null vs 0 in stats; `FA_OUTPUT_DIR` isolation; HMAC+PBKDF2 not JWT library.

## 13. Do not modify casually

ByteTrack yaml, `IdentityManager`, ball `predict` path, `CoordinateLogger` conventions, `possession.py`, `passes.py`, `turnovers.py`, `shots.py`, `team_assigner.py` unless the task is explicitly about them. Product jobs assume their CSV schemas.

## 14. Current development priorities (suggested, not committed)

1. Portable project root.  
2. ~~Identity fragmentation~~ (resolved offline 2026-09-23; extend validation to more clips).  
2b. ~~Camera-pose-independent goal geometry~~ (goal detector, 2026-09-23; needs footage from more venues).  
3. `events[]` or hide timeline.  
4. Tests + requirements pin.  
5. Calibrated goals / homography (future).

## 15–16. How to run / example commands

```
pip install -r requirements-api.txt
# also: ultralytics torch opencv pandas numpy (no pin file)
# identity resolution: see requirements-identity.txt (boxmot must be --no-deps)

python scripts/download_model.py

python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
cd frontend && npm install && npm run dev

python -m scripts.pipeline.run_mvp --video videos/raw/match.mp4 --start-time 200 --duration 40 --force-track
```

`--video` default is `videos/test/match_test.mp4` (too short for start=200). Videos are gitignored.

`set FA_OUTPUT_DIR=...` to isolate outputs.

`python -m tests.test_shots` (or pytest) checks shot/goal rules on synthetic panning scenes. `python scripts/test.py` prints torch/CUDA.

## 17. Important configuration values

From `config/config.py`: YOLO `models/yolo11n.pt (ball), yolo11m.pt (persons), lmbn_n_duke.pt (ReID) — scripts/download_model.py`; person track `imgsz=1280 conf=0.30`; ball class 32 conf 0.10 imgsz 1280; all timing in seconds, converted per video fps; interp 0.25 s; possession radius 0.75 body heights, ball must move with the player (<= 4 BH/s), a challenger must be 0.6x closer, one player's spells within 1 s merge; confirm 0.08 s; identity gap 220, distance = `min(40 + gap * 1080/fps, 550)` px (adaptive, not flat), appearance gate = two-region HS histogram Bhattacharyya ≤0.55 (only enforced past gap 20), height-ratio ≤2.0 (only past 6 samples); teams min samples 8 det conf 0.45 stride 5; pass gap 2 s, min possession 0.08 s, missing 0.50; intercept/recovery gap 2 s; goals detected every 0.1 s (`GOAL_*`); shots `SHOT_*` in goal-box heights and body heights per second; teams from identity kit groups (`GOALKEEPER_*`).

ByteTrack: high 0.5 low 0.1 new 0.6 buffer 90 match 0.8 fuse_score true.

Identity resolution: see `IDENTITY_*` block in `config.py` and docs/architecture.md *Identity resolution*.

## 18. Output locations

CLI: `outputs/coordinates|events|analytics|teams|heatmaps|tracking|identity`.  
Product: `outputs/matches/{match_id}/` including `analytics/match_stats.json`.  
Uploads: `data/uploads/{id}/`. Index: `data/matches_index.json`.

## 19. Known bugs / issues (do not silently “fix” unless asked)

- Hardcoded `D:\FootballAnalytics`.  
- Identity: resolved offline; unverified for other venues/kits (turf HSV + hue-based kit grouping).  
- Timeline empty by contract.  
- Video HEAD 405.  
- `config.py` prints and mkdirs on import.  
- Dual inference cost.  
- `detect.py` leftover.  
- Auth not production.  
- OpenCV version on one machine reported as 5.0.0 (verify locally).

## 20. Safe extension points

- Frontend: video player using existing `/video` or `/analysis-video`; charts; `events[]` **in match_stats** if adding timeline data.  
- `match_stats.py` aggregation (without changing event CSVs).  
- API metadata, multi-worker (careful with GPU).  
- Tests around `classify_transition` / `classify_turnover_pair` / `classify_shot` with fixture CSVs.  
- Portable config via env for `PROJECT_ROOT`.

Avoid adding xG, tackles, or “unique player ID” without new models and a product decision on false positives.
