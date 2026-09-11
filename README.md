# Crop Pest & Disease Detection API

A FastAPI backend that detects pests and diseases in crop images with a **YOLO**
model (Ultralytics). Upload a leaf/plant photo → the API runs inference, saves
the scan with every detection into a SQLite history, and returns pixel bounding
boxes a frontend can draw on the image. Includes a training pipeline so you can
fine-tune YOLO on your own pest/disease dataset.

On top of detection, the platform adds a full crop-health intelligence layer:
weather-based **risk forecasting**, **multilingual IPM advisories** (English,
Hindi, Marathi, Tamil, Telugu), **field reports**, **expert validation** with a
learning loop back into training, **geospatial hotspot mapping** and an
**officials dashboard**.

## Features

- `POST /api/detect` — image upload + field context (location, crop, stage) → detections + stored scan
- **Weather risk forecasting** — per-pest risk from the Open-Meteo forecast + recent local outbreaks (cached on disk for offline use, provider is swappable)
- **Multilingual advisories** — IPM management steps, safe pesticide use, expert referral and follow-up schedules in en/hi/mr/ta/te (local JSON, works offline)
- **Field reports** — farmer/extension observations without a photo, feeding risk + hotspots
- **Expert validation** — confirm / reject / needs-lab verdicts on scans and reports
- **Learning loop** — `scripts/export_training.py` turns expert-confirmed scans into a YOLO dataset for retraining
- **Hotspots & dashboard** — grid-clustered outbreak map + trend/top-pest statistics
- **Scan history** — every scan stored in SQLite with the original + annotated image
- **Training pipeline** — Roboflow dataset download + `train.py` → `models/custom.pt`
- Model auto-fallback — runs with a stock YOLOv8n until you train your own weights (a corrupt/empty `custom.pt` no longer takes the service down)
- CORS enabled — plug in any web frontend later

## Project layout

```
app/
  main.py            FastAPI app, CORS, startup (loads model once)
  config.py          Settings from .env / environment variables
  database.py        SQLite engine + session + lightweight migrations
  models.py          Scan, Detection, FieldReport, ExpertReview tables
  schemas.py         Response models + serializers
  detector.py        YOLO wrapper (lazy ultralytics import, resilient fallback)
  routers/
    detect.py        POST /api/detect (+ location/crop/stage form fields)
    scans.py         history + image endpoints
    info.py          /api/health, /api/classes
    risk.py          GET /api/risk — weather-based pest risk
    advisories.py    GET /api/advisory, /api/advisories, /api/languages
    reports.py       POST/GET /api/reports — field observations
    reviews.py       POST/GET /api/reviews — expert verdicts + pending queue
    insights.py      GET /api/hotspots, /api/stats/summary
  services/
    weather.py       WeatherProvider interface + Open-Meteo + disk cache
    risk.py          Rule engine over data/pest_rules.json
    advisory.py      Localized advisory lookup over data/advisories.json
    geo.py           Haversine distance helper
scripts/
  train.py                 Train YOLO on your dataset
  download_roboflow.py     Pull a dataset from Roboflow
  export_training.py       Export expert-validated scans as a YOLO dataset
  make_sample.py           Generate a test image
models/              custom.pt  (your trained weights — used at startup)
uploads/             original + annotated images
data/                datasets, scans.db, pest_rules.json, advisories.json
static/index.html    Plain-HTML upload page (served at /)
streamlit_app.py     Role-based UI: scan, risk, reports, review, dashboard
```

## Requirements

- Python **3.10+**
- The ML stack (**ultralytics** + **PyTorch**, ~1–2 GB) — only needed for real
  inference and training. See Installation.

## Installation

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate      macOS/Linux:  source .venv/bin/activate

pip install -r requirements.txt        # full stack (inference + training)
cp .env.example .env                   # optional — defaults already work
```

> **PyTorch size tip (GPU-less machines):** installing `requirements.txt` pulls
> PyTorch with CUDA binaries on Linux/Windows. If you have no GPU, install the
> CPU build first to keep it small:
>
> ```bash
> pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
> pip install -r requirements.txt
> ```
>
> Just running/tests without inference? `pip install -r requirements-dev.txt`
> is enough — the model is imported lazily.

## Running the API

```bash
uvicorn app.main:app --reload
```

Open the interactive docs at **http://127.0.0.1:8000/docs**.

On startup the app loads `models/custom.pt`. If it doesn't exist yet, it falls
back to the pretrained `yolov8n.pt` (auto-downloaded once) so the API works
end-to-end — but its classes are generic COCO objects, so **train your own
model** (below) for real pest/disease results.

Generate a sample image and test detection:

```bash
python scripts/make_sample.py
curl -s -X POST http://127.0.0.1:8000/api/detect \
  -F "file=@data/sample.jpg" | python -m json.tool
```

Response:

```json
{
  "id": 1,
  "filename": "sample.jpg",
  "status": "affected",
  "model_version": "custom.pt",
  "image_width": 640,
  "image_height": 640,
  "created_at": "2026-09-04T12:00:00",
  "detection_count": 2,
  "detections": [
    {
      "class_name": "rice_blast",
      "confidence": 0.87,
      "bbox": { "x": 120, "y": 90, "width": 210, "height": 160 }
    }
  ],
  "image_url": "/api/scans/1/image",
  "annotated_url": "/api/scans/1/annotated"
}
```

`status` is `affected` when at least one detection above the confidence
threshold is not in `HEALTHY_CLASSES`, otherwise `healthy`.

## API reference

| Method | Path | Description |
|---|---|---|
| POST | `/api/detect` | Multipart upload (`file` field) → runs the model, stores the scan, returns detail |
| GET | `/api/scans?skip=0&limit=20` | Paginated scan history, newest first |
| GET | `/api/scans/{id}` | One scan with all detections |
| GET | `/api/scans/{id}/image` | The original uploaded image |
| GET | `/api/scans/{id}/annotated` | The image with YOLO boxes drawn |
| GET | `/api/health` | Model loaded? weights? device? error? |
| GET | `/api/classes` | Class names the loaded model detects |
| GET | `/api/risk?location=&crop=&crop_stage=` | Weather-based per-pest risk (or `?lat=&lon=`) |
| GET | `/api/advisory?class_name=&lang=` | Localized IPM advisory (en/hi/mr/ta/te) |
| GET | `/api/advisories` | List advisory targets |
| GET | `/api/languages` | Supported advisory languages |
| POST | `/api/reports` | Submit a field observation (JSON) |
| GET | `/api/reports` | List field reports |
| POST | `/api/reviews` | Expert verdict on a scan or report |
| GET | `/api/reviews/pending` | Validation queue (unreviewed scans) |
| GET | `/api/hotspots?days=14` | Grid-clustered outbreak hotspots |
| GET | `/api/stats/summary` | Dashboard totals, top pests, 14-day trend |

## Training your own model

### 1. Get a dataset (two options)

**A. Roboflow (easiest)** — pick a public pest/disease dataset or export your
own annotations, then:

```bash
python scripts/download_roboflow.py \
  --workspace my-workspace --project my-crop-project --version 1
# needs ROBOFLOW_API_KEY in .env (https://app.roboflow.com/settings/api)
```

**B. Your own YOLO-format data** — a folder like:

```
data/mydataset/
  images/
    train/  *.jpg
    val/    *.jpg
  labels/
    train/  *.txt   (YOLO label files)
    val/    *.txt
  data.yaml            # names: [rice_blast, leaf_rust, healthy]
```

`data.yaml` needs a `names:` list of your classes (use short lowercase names,
no spaces). Ultralytics auto-splits further if you only have train/val.

### 2. Train

```bash
python scripts/train.py --data data/mydataset/data.yaml \
  --model yolov8n.pt --epochs 100
```

- `--model` sizes: `yolov8n/s/m/l` (nano → large). Start with `n` or `s` on CPU.
- GPU machines: omit `--device` (auto CUDA). CPU-only: `--device cpu`.
- Results land in `runs/detect/<name>/`; **best weights are copied to
  `models/custom.pt`** automatically.

### 3. Use it

Restart the API — it now loads `models/custom.pt` and `/api/classes` shows your
pest/disease classes:

```bash
uvicorn app.main:app --reload
```

If your dataset includes a `healthy` class, the `.env` default
`HEALTHY_CLASSES=["healthy"]` ensures scans of healthy leaves get `status:
"healthy"` instead of `"affected"`. Remove/adjust that line if your classes
differ.

## Configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `MODEL_PATH` | `models/custom.pt` | Trained weights loaded at startup |
| `FALLBACK_MODEL` | `yolov8n.pt` | Auto-downloaded if `MODEL_PATH` is missing |
| `CONFIDENCE_THRESHOLD` | `0.25` | Min confidence to keep a detection |
| `IOU_THRESHOLD` | `0.45` | NMS IoU threshold |
| `IMAGE_SIZE` | `640` | Inference resolution |
| `DEVICE` | *(auto)* | `cpu`, `cuda:0`, or empty for auto |
| `DATABASE_URL` | `sqlite:///./data/scans.db` | Scan history DB |
| `UPLOAD_DIR` | `uploads` | Where images are stored |
| `MAX_UPLOAD_MB` | `20` | Max upload size |
| `HEALTHY_CLASSES` | `[]` | Classes that never trigger "affected" |
| `CORS_ORIGINS` | `["*"]` | Allowed browser origins (JSON list) |
| `WEATHER_PROVIDER` | `open-meteo` | Weather source (swappable; offline sources can be added) |
| `WEATHER_CACHE_TTL_HOURS` | `24` | How long a forecast stays fresh on disk |
| `WEATHER_CACHE_PATH` | `data/weather_cache.json` | Forecast cache (offline lifeline) |
| `ROBOFLOW_API_KEY` | *(empty)* | For `scripts/download_roboflow.py` |

## Streamlit frontend (optional)

A role-based UI that talks to the same API over HTTP — **no ML stack needed on
the machine running it**. Sign in as Farmer, Extension worker or Official to get
different pages:

- **🔎 Scan crop** — photo + village/GPS + crop/stage → detection boxes, then a
  **localized advisory panel** (language picked in the sidebar) with IPM steps,
  safe-use warnings and follow-up schedule
- **🌦 Risk forecast** — per-pest risk for any village with the weather drivers
  behind every score
- **📝 Field report** — observations without a photo
- **✅ Expert review** — confirm / reject / needs-lab on scans and reports
- **📊 Dashboard** — hotspots map, 14-day trend, top pests (officials)

```bash
pip install -r requirements.txt            # adds streamlit + requests
streamlit run streamlit_app.py              # UI on http://127.0.0.1:8501
```

Start the FastAPI backend first (`uvicorn app.main:app`). Point the sidebar
"API URL" at a different backend to use a remote server, or set the
`API_URL` env var.

## Learning loop (expert validation → retraining)

1. Experts review scans via `POST /api/reviews` (verdict `confirmed`,
   `rejected` or `needs_lab`) or in the Streamlit Expert review page.
2. Export the validated data as a YOLO dataset:

   ```bash
   python scripts/export_training.py --out data/expert_dataset
   ```

   Confirmed scans become labeled images (with any corrected class applied);
   rejected scans become background images.
3. Retrain and the API picks the new weights up on restart:

   ```bash
   python scripts/train.py --data data/expert_dataset/data.yaml --epochs 50
   ```

## Offline readiness

The system is designed to degrade gracefully without internet:

- **Advisories, risk rules and languages** are local JSON files — always work.
- **Weather** is cached to `data/weather_cache.json` for 24 h; after one
  successful fetch per location, forecasts keep working offline (responses are
  flagged `weather_stale`).
- The `WeatherProvider` interface (`app/services/weather.py`) is the single
  integration point for a future fully-offline source (manual entry, on-farm
  sensors, bundled climatology tables) — implement the two methods and set
  `WEATHER_PROVIDER`.

## Android app & full offline mode (PWA)

The web page at `http://<server>:8000/` is an installable **Progressive Web
App** — open it once on an Android phone and it becomes an app with a
home-screen icon, running full-screen like a native app.

**Install (one time, needs the server reachable):**

1. On the phone, open Chrome and go to `http://<your-PC-IP>:8000/`
   (find the PC's IP with `ipconfig`; the API must be started with
   `--host 0.0.0.0` to accept LAN connections).
2. Tap the **"Install app"** banner (or Chrome menu → *Add to Home screen*).
   On iPhone: *Share → Add to Home Screen*.

**What works offline (no internet, no server):**

- Taking/uploading crop photos and scanning them into the **offline queue**.
- The **advisory library** in all 5 languages and the **risk rules**, cached
  from `GET /api/offline/bundle` (ETag-based, refreshed at most daily).
- Previously cached pages — the app shell survives airplane mode.

**When connectivity returns** (Background Sync, or the "Try syncing now"
button), queued scans replay automatically as normal `POST /api/detect`
calls — with their field context — and land in the server's scan history,
feeding the dashboard, hotspots and expert review like any other scan.

**Limits:** detection inference itself always runs on the server, so queued
scans show results only after sync. Fully serverless on-device inference would
need a native app with TensorFlow Lite (see Next steps).

Files: `static/manifest.webmanifest`, `static/sw.js`, `static/offline.html`,
`static/icons/`, and the `offline` router (`app/routers/offline.py`).

## One-command start (Windows)

Start both the API and Streamlit together, wait for them, and open the browser:

- **Double-click `start.bat`** — runs both servers and opens `http://127.0.0.1:8501`.
- **Double-click `stop.bat`** — shuts both down.

Both are idempotent: re-running `start.bat` when the servers are already up
just reports "already running". The servers detach, so you can close the
console window and they keep running. From WSL directly, use
`wsl -d Ubuntu-26.04 -- bash ./run_all.sh`.

> If ports stop answering after a WSL restart, run `wsl --shutdown` then
> `start.bat` again — that rebuilds localhost forwarding.

## Verification with Reticle (browser-level)

The repo is wired to [Reticle](https://docs.reticle.sh) — an MCP server that
verifies the running app from inside the real browser (DOM, network, console)
and returns a verdict, not a screenshot. The repo is linked to the Reticle
Cloud workspace (`project: default`); `verify` runs auto-push there.

- **Saved flow:** `.reticle/flows/default/farmer-scan-journey.json` — the core
  journey *farmer uploads a crop photo → POST /api/detect → app signals
  `scan:result` when the result renders*. The app fires that signal itself
  (`reticle.signal`), which is the strongest evidence grade Reticle offers.
- **Replay the flow** (headless, exit code 0 = pass):
  ```bash
  # inside WSL, project root, with Node on PATH (see .reticle-tools/):
  npx @reticlehq/server verify http://127.0.0.1:8000/ --timeout 60000
  ```
- **Interactive driving**: start the daemon (`npx @reticlehq/server serve`),
  then use the `reticle_*` MCP tools from your coding agent, or the small HTTP
  client at `.reticle-tools/reticle_client.mjs` (docs: HTTP transport).
- **Setup notes**: the SDK is vendored at `static/vendor/reticle.js`
  (@reticlehq/browser@2.13.1) and connects only on localhost/127.0.0.1 —
  phones using the PWA never load it. `data-testid` attributes on the upload
  input, status badge and detection list are Reticle's stable anchors.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

The suite stubs the YOLO model, so it runs without PyTorch/ultralytics while
still exercising upload validation, inference storage, history listing, image
serving, error paths — plus the risk engine, advisories in every language,
field reports, expert reviews, hotspots and dashboard stats.

## Next steps / ideas

- Train a real pest model (the current fallback returns generic COCO classes).
- Swap in an offline weather provider for full no-internet operation.
- Add user accounts so each farmer/field keeps its own history.
- Ship the detector **on-device**: export the trained model to TensorFlow Lite
  and build an Android wrapper (Capacitor/TWA) around this same UI — then
  detection itself works with no server at all.
- Push hotspots to officials via SMS/WhatsApp notifications.
- Export the trained model to ONNX/TensorRT for faster, lighter deployment.
