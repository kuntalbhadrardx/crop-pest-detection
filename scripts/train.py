#!/usr/bin/env python3
"""Train a YOLO detector on a pest/disease dataset.

Requires the full ML deps:  pip install -r requirements.txt

Example (dataset in YOLO format with a data.yaml):
    python scripts/train.py --data data/roboflow/data.yaml \
        --model yolov8n.pt --epochs 100

When training finishes, the best weights are copied to models/custom.pt and
the API picks them up on the next restart.
"""
import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--data",
        type=Path,
        default=ROOT / "data" / "data.yaml",
        help="Path to the dataset data.yaml (or a folder containing it).",
    )
    p.add_argument(
        "--model",
        default="yolov8n.pt",
        help="Base weights: a file (e.g. models/custom.pt) or a name like "
        "yolov8n.pt / yolov8s.pt / yolov8m.pt / yolov8l.pt (auto-downloaded).",
    )
    p.add_argument("--epochs", type=int, default=100, help="Training epochs.")
    p.add_argument("--imgsz", type=int, default=640, help="Training image size.")
    p.add_argument(
        "--batch",
        type=int,
        default=-1,
        help="Batch size (-1 = auto-select from GPU memory).",
    )
    p.add_argument(
        "--device",
        default=None,
        help="Device: omit for auto (CUDA if present), 'cpu', or 'cuda:0'.",
    )
    p.add_argument(
        "--project",
        type=Path,
        default=ROOT / "runs" / "detect",
        help="Folder where Ultralytics writes its run output.",
    )
    p.add_argument("--name", default="train", help="Run name (subfolder of --project).")
    p.add_argument(
        "--save-to",
        type=Path,
        default=ROOT / "models" / "custom.pt",
        help="Where to copy the best weights (used by the API at startup).",
    )
    p.add_argument("--workers", type=int, default=8, help="Data loader workers.")
    return p.parse_args()


def resolve_data_yaml(data_arg: Path) -> Path:
    data_yaml = data_arg if data_arg.is_file() else data_arg / "data.yaml"
    if not data_yaml.is_file():
        sys.exit(
            f"Dataset YAML not found at {data_yaml}.\n"
            "Point --data at a YOLO-format dataset folder containing data.yaml "
            "(see README 'Preparing a dataset')."
        )
    return data_yaml


def main() -> None:
    args = parse_args()
    data_yaml = resolve_data_yaml(args.data)

    # Basic sanity check on the dataset YAML.
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        sys.exit(f"PyYAML is required for training: {exc}")
    with open(data_yaml, encoding="utf-8") as fh:
        dataset = yaml.safe_load(fh) or {}
    names = dataset.get("names") or dataset.get("nc")
    if not names:
        sys.exit(
            f"{data_yaml} has no 'names' list. Add e.g.\n"
            "names:\n  - rice_blast\n  - leaf_rust\n  - healthy"
        )
    print(f"Dataset: {data_yaml}")
    print(f"Classes : {names}")

    from ultralytics import YOLO  # heavy import, only needed here

    print(f"Loading base model: {args.model}")
    model = YOLO(args.model)

    train_kwargs = dict(
        data=str(data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        project=str(args.project),
        name=args.name,
        exist_ok=True,
        workers=args.workers,
    )
    if args.device:
        train_kwargs["device"] = args.device

    print(f"Starting training ({args.epochs} epochs, imgsz={args.imgsz})…")
    model.train(**train_kwargs)

    best = Path(args.project) / args.name / "weights" / "best.pt"
    if not best.is_file():
        sys.exit(f"Expected best weights at {best} but they are missing.")

    save_to = args.save_to if args.save_to.is_absolute() else ROOT / args.save_to
    save_to.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(best, save_to)
    print(f"\nTraining done. Best weights copied to {save_to}")
    print("Restart the API (uvicorn app.main:app) to load the new model.")
    print(f"Check results: {Path(args.project) / args.name}")


if __name__ == "__main__":
    main()
