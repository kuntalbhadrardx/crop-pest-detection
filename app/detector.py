"""YOLO detection wrapper.

``ultralytics`` is imported lazily (inside :meth:`Detector._load`) so the API
can boot — and the test suite can run — before the heavy ML dependencies
(ultralytics + PyTorch, ~1-2 GB) are installed.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .config import Settings

logger = logging.getLogger(__name__)


class Detector:
    """Loads a YOLO model once and runs detection on images."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model: Any = None
        self.model_version: str | None = None
        self.is_fallback: bool = False
        self.device: str = "unknown"
        self.error: str | None = None
        try:
            self._load()
        except Exception as exc:  # keep API alive; /api/health reports the error
            self.error = f"{type(exc).__name__}: {exc}"
            logger.exception("Failed to load YOLO model")

    # -- properties ------------------------------------------------------
    @property
    def available(self) -> bool:
        return self.model is not None

    @property
    def names(self) -> list[str]:
        return list(self.names_map.values())

    @property
    def names_map(self) -> dict[int, str]:
        if self.model is None:
            return {}
        return dict(self.model.names)

    # -- loading ---------------------------------------------------------
    def _load(self) -> None:
        try:
            from ultralytics import YOLO
        except ImportError as exc:  # pragma: no cover - depends on install
            raise RuntimeError(
                "ultralytics is not installed. Run: pip install -r requirements.txt"
            ) from exc

        model_path = Path(self.settings.model_path)
        if model_path.exists():
            source = str(model_path)
            self.model_version = model_path.name
            self.is_fallback = False
            logger.info("Loading custom YOLO model: %s", model_path)
        else:
            source = self.settings.fallback_model
            self.model_version = self.settings.fallback_model
            self.is_fallback = True
            logger.warning(
                "No custom model at %s — falling back to pretrained %s "
                "(auto-downloaded on first run). Train one with scripts/train.py.",
                model_path,
                source,
            )

        self.model = YOLO(source)

        try:
            device = getattr(self.model, "device", None)
            self.device = str(device) if device else (self.settings.device or "auto")
        except Exception:  # device not resolved until first inference
            self.device = self.settings.device or "auto"

    # -- inference -------------------------------------------------------
    def predict(self, image_path: Path | str, annotated_path: Path | str | None = None) -> dict:
        """Run detection on one image.

        Returns:
            dict with keys ``detections`` (list of {class_name, confidence,
            bbox: {x, y, width, height}} in pixels), ``image_width``,
            ``image_height``, and ``annotated_path`` (saved image or None).
        """
        if self.model is None:
            raise RuntimeError(self.error or "Model is not loaded")

        kwargs: dict[str, Any] = dict(
            source=str(image_path),
            conf=self.settings.confidence_threshold,
            iou=self.settings.iou_threshold,
            imgsz=self.settings.image_size,
            verbose=False,
        )
        if self.settings.device:
            kwargs["device"] = self.settings.device

        results = self.model.predict(**kwargs)
        result = results[0]

        detections: list[dict] = []
        boxes = getattr(result, "boxes", None)
        if boxes is not None and len(boxes) > 0:
            names = result.names
            for box in boxes:
                x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
                detections.append(
                    {
                        "class_name": names[int(box.cls[0])],
                        "confidence": round(float(box.conf[0]), 4),
                        "bbox": {
                            "x": round(x1, 2),
                            "y": round(y1, 2),
                            "width": round(x2 - x1, 2),
                            "height": round(y2 - y1, 2),
                        },
                    }
                )

        annotated = None
        if annotated_path is not None:
            annotated = self._save_annotated(result, Path(annotated_path))

        height, width = (int(v) for v in result.orig_shape)
        return {
            "detections": detections,
            "image_width": width,
            "image_height": height,
            "annotated_path": annotated,
        }

    @staticmethod
    def _save_annotated(result: Any, out_path: Path) -> str:
        """Draw detection boxes/labels onto the original image and save as JPEG."""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        from PIL import Image

        plotted = result.plot(line_width=3, conf=True)  # RGB numpy array
        Image.fromarray(plotted).save(str(out_path), format="JPEG")
        return str(out_path)
