#!/usr/bin/env python3
"""Download a Roboflow dataset (YOLO format) into data/.

Find your workspace/project/version on the Roboflow dataset page
(https://app.roboflow.com/<workspace>/<project>/<version>) or in their export
snippet, then run:

    python scripts/download_roboflow.py \
        --workspace my-workspace --project my-crop-project --version 1

The API key comes from the ROBOFLOW_API_KEY env var / .env, or --api-key.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", required=True, help="Roboflow workspace name.")
    p.add_argument("--project", required=True, help="Roboflow project name.")
    p.add_argument("--version", type=int, default=1, help="Dataset version number.")
    p.add_argument(
        "--api-key",
        default="",
        help="Roboflow API key (or set ROBOFLOW_API_KEY).",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "roboflow",
        help="Destination folder for the downloaded dataset.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    api_key = args.api_key

    if not api_key:
        try:
            from dotenv import load_dotenv

            load_dotenv(ROOT / ".env")
        except ImportError:
            pass
        import os

        api_key = os.environ.get("ROBOFLOW_API_KEY", "")

    if not api_key:
        sys.exit(
            "No Roboflow API key found. Pass --api-key or set ROBOFLOW_API_KEY "
            "in .env (get one at https://app.roboflow.com/settings/api)."
        )

    try:
        from roboflow import Roboflow
    except ImportError as exc:  # pragma: no cover
        sys.exit(f"roboflow package missing. Run: pip install roboflow ({exc})")

    output = args.output if args.output.is_absolute() else ROOT / args.output
    print(
        f"Downloading {args.workspace}/{args.project} v{args.version} "
        f"(yolov8 format) into {output} …"
    )
    rf = Roboflow(api_key=api_key)
    project = rf.workspace(args.workspace).project(args.project)
    dataset = project.version(args.version).download("yolov8", location=str(output))

    data_yaml = Path(dataset.location) / "data.yaml"
    print(f"Done. Train with:\n  python scripts/train.py --data {data_yaml}")


if __name__ == "__main__":
    main()
