# Deploying for free (no card needed)

| Piece | Service | What it does |
|---|---|---|
| Website | Vercel | Serves the React app in `frontend/` |
| API, logins, match list | Render (free web service) | Runs `app/` (FastAPI). No GPU, no torch |
| Videos and results | Backblaze B2 (10 GB free, no card) | Uploads, stats JSON, analysis videos, and the small `users.json` / `matches_index.json` files |
| Analysis | Kaggle notebook (about 30 GPU hours a week, T4) | Runs `scripts/cloud/worker.py`, started by the API when a match is queued |

Any S3-compatible bucket works for storage (Cloudflare R2 too, but R2 wants a card).

How a match flows:

1. The browser asks the API for upload links and sends the video straight to the bucket in 64 MB parts.
2. "Start analysis" queues the match. The API pushes a private Kaggle notebook, which clones this repo at the commit Render is running, installs the packages and starts the worker.
3. The worker claims the match, downloads it, runs the normal pipeline on the GPU, sends progress every minute and uploads the stats and analysis video to the bucket.
4. When the queue is empty for a couple of minutes the notebook stops, so it doesn't burn GPU hours.

If the worker goes quiet for 15 minutes the match goes back in the queue (once), and a new notebook is started.

Render's free Postgres is deleted after 30 days, which is why logins and the match list are JSON files in the bucket instead.

Keep API keys out of chats, screenshots and the repo. They only go into Render's environment variables. If one leaks, delete it and make a new one.

## 1. Backblaze B2

1. Sign up at backblaze.com (B2 Cloud Storage). Email and password only.
2. Buckets > Create a Bucket: a unique name (e.g. `tactivision-yourname`), **Private**.
3. Note the bucket's **Endpoint**, e.g. `s3.us-east-005.backblazeb2.com`. The region is the middle part, `us-east-005`.
4. Application Keys > Add a New Application Key: access to **All** buckets, **Read and Write**. Copy the **keyID** and **applicationKey** (shown once).

The API sets the bucket's CORS rules itself on startup (the browser needs them to upload parts and read their ETags). If the Render log says it couldn't, the key is missing the `writeBuckets` capability: make a new key for all buckets.

Free limits without a card: 10 GB stored, **1 GB downloaded per day** and 2,500 reads a day, reset at midnight GMT. A full 37-minute match costs about 760 MB (Kaggle downloading the upload) plus about 150 MB each time someone watches its Tracking video. So plan on about one full match a day; short clips are no problem. Uploads don't count.

## 2. Kaggle

1. Sign up at kaggle.com.
2. Settings > **Phone verification**. Without it notebooks get no GPU and no internet.
3. Settings > API > **Create Legacy API Key**. It downloads `kaggle.json` with your `username` and `key`. (If you only get the new kind of token, set `KAGGLE_API_TOKEN` instead of `KAGGLE_KEY`.)

Nothing else to set up: the API creates the `fa-analysis-worker` notebook on the first analysis.

## 3. Render (API)

1. Sign up at render.com with GitHub.
2. New > **Web Service** > pick the repo. (Blueprint also works with `render.yaml`, but some accounts get asked for a card there.)

| Field | Value |
|---|---|
| Runtime | Python 3 |
| Build command | `pip install -r requirements-api.txt` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Instance type | Free |
| Health check path | `/api/health` |

3. Environment variables:

| Key | Value |
|---|---|
| `PYTHON_VERSION` | `3.12.7` |
| `FA_STORAGE` | `s3` |
| `FA_RUNNER` | `kaggle` |
| `FA_SECRET` | Generate |
| `FA_WORKER_TOKEN` | Generate |
| `FA_ALLOWED_ORIGINS` | your Vercel URL (use `http://localhost:5173` until you have it) |
| `S3_ENDPOINT` | `https://s3.us-east-005.backblazeb2.com` (yours) |
| `S3_REGION` | `us-east-005` (yours) |
| `S3_BUCKET` | your bucket name |
| `S3_ACCESS_KEY_ID` | B2 keyID |
| `S3_SECRET_ACCESS_KEY` | B2 applicationKey |
| `KAGGLE_USERNAME` | from `kaggle.json` |
| `KAGGLE_KEY` | from `kaggle.json` |

Render also sets `RENDER_EXTERNAL_URL` (where the worker calls back) and `RENDER_GIT_COMMIT` (which commit the worker runs).

4. Deploy, then open `https://YOUR-API.onrender.com/api/health`. It should say `{"ok":true}`.

## 4. Vercel (website)

1. vercel.com > sign up with GitHub > Add New > Project > import the repo.
2. **Root Directory: `frontend`** (Vite is detected).
3. Environment variable `VITE_API_URL` = your Render URL, no trailing slash.
4. Deploy. Put the site URL into `FA_ALLOWED_ORIGINS` on Render (comma separated if several) and save; Render redeploys and adds the same origins to the bucket's CORS rules.

## 5. First run

1. Open the site, sign up, upload a short clip and pick a **custom window** of about 60 seconds.
2. The processing page shows "Starting a cloud GPU..." for the first few minutes (the notebook boots and installs packages).
3. Watch it at kaggle.com/code/YOUR-USERNAME/fa-analysis-worker (Logs).

## Things to know

- **Render sleeps** after 15 minutes without visitors. The first page load then takes about a minute (the site shows a "waking up" note). While a match is analysed the worker's heartbeats keep it awake.
- **GPU hours:** a full 37-minute match takes roughly 3-4 hours on a T4. When the weekly hours run out, Kaggle either refuses the notebook (the API retries every 10 minutes) or starts it without a GPU (the worker notices, stops, and matches wait with "Free GPU hours are used up for now" for an hour at a time) until the quota resets.
- **One GPU at a time:** Kaggle's free tier runs one GPU notebook per account, so matches are analysed one after another.
- **Storage:** uploads stop at 9 GB used (`FA_STORAGE_LIMIT_GB`). After a match is analysed the original upload is deleted and only the analysis video (which shows the footage too) is kept. Set `FA_KEEP_SOURCE_VIDEO=1` to keep uploads. Deleting a match removes its files.
- **Smaller Tracking video:** the cloud worker renders it at 960 px wide, CRF 28 (about a third of the local size) because of the daily download limit. `FA_ANALYSIS_VIDEO_WIDTH` / `FA_ANALYSIS_VIDEO_CRF` change it.
- **12-hour limit:** Kaggle stops a notebook after 12 hours, so the worker doesn't start a new match after 8 hours running (`FA_WORKER_MAX_HOURS`); the next notebook picks it up.
- **Kaggle's rules** are written for data-science work. Running a personal or portfolio project like this is fine; don't build a paid service on it.

## Other ways to run the worker

The worker only needs the API address and token, so any machine with a GPU can do the analysis:

```bash
FA_API_URL=https://YOUR-API.onrender.com FA_WORKER_TOKEN=... python -m scripts.cloud.worker
```

Set `FA_RUNNER=external` on Render if you only want to use your own workers.

## Running everything locally

Nothing changes: `FA_STORAGE` and `FA_RUNNER` default to `local`, files stay under `data/`, and analysis runs on this machine.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `FA_STORAGE` | `local` | `local` (data/) or `s3` |
| `FA_RUNNER` | `local` | `local`, `kaggle` or `external` |
| `S3_REGION` | from a B2 endpoint, else `auto` | signing region |
| `FA_MAX_UPLOAD_GB` | 8 | largest upload |
| `FA_STORAGE_LIMIT_GB` | 9 with s3 | refuse uploads above this total |
| `FA_KEEP_SOURCE_VIDEO` | 0 with s3 | keep the upload after analysis |
| `FA_WORKER_STALE_S` | 900 | silence before a job is requeued |
| `FA_KAGGLE_BOOT_S` | 1200 | time a new notebook gets to check in |
| `FA_ALLOWED_ORIGIN_REGEX` | | e.g. `https://tactivision-.*\.vercel\.app` for preview deploys |
| `FA_GIT_REF` | Render commit | code the worker runs |
| `FA_FOOTAGE_CHECK` | 1 | 0 skips the quick "is this football?" check (about 20 frames need green turf with players on it) |
