"""Pydantic response schemas + ORM -> schema helpers."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from .models import Detection, Scan


class BBox(BaseModel):
    """Pixel bounding box (top-left corner + size) in the original image."""

    x: float
    y: float
    width: float
    height: float


class DetectionItem(BaseModel):
    class_name: str
    confidence: float
    bbox: BBox


class ScanDetail(BaseModel):
    id: int
    filename: str
    status: str  # "healthy" | "affected"
    model_version: str
    image_width: int
    image_height: int
    created_at: datetime
    detection_count: int
    detections: list[DetectionItem] = []
    image_url: str
    annotated_url: str | None = None


class ScanSummary(BaseModel):
    """Lightweight row used in the history list."""

    id: int
    filename: str
    status: str
    model_version: str
    created_at: datetime
    detection_count: int
    image_url: str
    annotated_url: str | None = None


class ScanListResponse(BaseModel):
    total: int
    items: list[ScanSummary]


class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded"
    model_loaded: bool
    model_version: str | None = None
    fallback_in_use: bool | None = None
    device: str | None = None
    class_count: int | None = None
    error: str | None = None


class ClassInfo(BaseModel):
    id: int
    name: str


class ClassesResponse(BaseModel):
    count: int
    classes: list[ClassInfo]


# ---------------------------------------------------------------------------
# ORM -> schema helpers
# ---------------------------------------------------------------------------
def _urls(scan_id: int) -> tuple[str, str | None]:
    return f"/api/scans/{scan_id}/image", f"/api/scans/{scan_id}/annotated"


def detection_item(det: Detection) -> DetectionItem:
    return DetectionItem(
        class_name=det.class_name,
        confidence=det.confidence,
        bbox=BBox(x=det.bbox_x, y=det.bbox_y, width=det.bbox_w, height=det.bbox_h),
    )


def detail_from_scan(scan: Scan) -> ScanDetail:
    image_url, annotated_url = _urls(scan.id)
    return ScanDetail(
        id=scan.id,
        filename=scan.filename,
        status=scan.status,
        model_version=scan.model_version,
        image_width=scan.image_width,
        image_height=scan.image_height,
        created_at=scan.created_at,
        detection_count=len(scan.detections),
        detections=[detection_item(d) for d in scan.detections],
        image_url=image_url,
        annotated_url=annotated_url if scan.annotated_path else None,
    )


def summary_from_scan(scan: Scan) -> ScanSummary:
    image_url, annotated_url = _urls(scan.id)
    return ScanSummary(
        id=scan.id,
        filename=scan.filename,
        status=scan.status,
        model_version=scan.model_version,
        created_at=scan.created_at,
        detection_count=len(scan.detections),
        image_url=image_url,
        annotated_url=annotated_url if scan.annotated_path else None,
    )
