# Crop Pest & Disease Detection API

A FastAPI backend that detects pests and diseases in crop images with a **YOLO**
model (Ultralytics). Upload a leaf/plant photo → the API runs inference, saves
the scan with every detection into a SQLite history, and returns pixel bounding
boxes a frontend can draw on the image. Includes a training pipeline so you can
fine-tune YOLO on your own pest/disease dataset.

## Features

- `POST /api/detect` — image upload → detection result (status, class, confidence, bbox)
- **Scan history** — every scan stored in SQLite with the original + annotated image
- **Training pipeline** — Roboflow dataset download + `train.py` → `models/custom.pt`
- Model auto-fallback — runs with a stock YOLOv8n until you train your own weights
- CORS enabled — plug in any web frontend later

## Project layout

```
app/
  main.py            FastAPI app, CORS, startup (loads model once)
  config.py          Settings from .env / environment variables
  database.py        SQLite engine + session
  models.py          Scan + Detection tables
  schemas.py         Response models + serializers
  detector.py        YOLO wrapper (lazy ultralytics import)
  routers/
    detect.py        POST /api/detect
    scans.py         history + image endpoints
    info.py          /api/health, /api/classes
scripts/
  train.py                 Train YOLO on your dataset
  download_roboflow.py     Pull a dataset from Roboflow
  make_sample.py           Generate a test image
models/              custom.pt  (your trained weights — used at startup)
uploads/             original + annotated images
data/                datasets + scans.db (SQLite)
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
| `ROBOFLOW_API_KEY` | *(empty)* | For `scripts/download_roboflow.py` |

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

The suite stubs the YOLO model, so it runs without PyTorch/ultralytics while
still exercising upload validation, inference storage, history listing, image
serving, and error paths.

## Next steps / ideas

- Frontend: upload form + draw the returned boxes on the image (`<canvas>`),
  list history with thumbnails.
- Add user accounts so each farmer/field keeps its own history.
- Run inference on a GPU server or containerize with Docker.
- Export the trained model to ONNX/TensorRT for faster, lighter deployment.
