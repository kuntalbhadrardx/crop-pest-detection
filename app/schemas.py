"""Pydantic response schemas + ORM -> schema helpers."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from .models import Detection, ExpertReview, FieldReport, Scan


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
    latitude: float | None = None
    longitude: float | None = None
    location_name: str | None = None
    crop: str | None = None
    crop_stage: str | None = None


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
    latitude: float | None = None
    longitude: float | None = None
    location_name: str | None = None
    crop: str | None = None
    crop_stage: str | None = None


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
# Risk forecasting
# ---------------------------------------------------------------------------
class WeatherDay(BaseModel):
    date: str
    rain_mm: float | None = None
    humidity_mean: float | None = None
    temp_max: float | None = None
    wind_max: float | None = None


class WeatherSummary(BaseModel):
    location: str | None = None
    latitude: float
    longitude: float
    source: str
    stale: bool = False
    days: list[WeatherDay]


class PestRisk(BaseModel):
    target: str
    score: float
    level: str  # low | medium | high | severe
    drivers: list[str] = []


class RiskResponse(BaseModel):
    location: str | None = None
    latitude: float
    longitude: float
    crop: str | None = None
    crop_stage: str | None = None
    overall_level: str
    per_pest: list[PestRisk]
    weather_summary: dict = {}
    history_driver: str | None = None
    weather_stale: bool = False


# ---------------------------------------------------------------------------
# Advisories
# ---------------------------------------------------------------------------
class ReferralInfo(BaseModel):
    title: str
    text: str
    followup_days: int | None = None


class AdvisoryResponse(BaseModel):
    target: str
    language: str
    name: str
    management: list[str] = []
    safety: list[str] = []
    followup_days: int | None = None
    referral: ReferralInfo | None = None
    available_languages: list[str] = []


class LanguagesResponse(BaseModel):
    count: int
    default: str
    languages: list[str]


class AdvisorySummary(BaseModel):
    target: str
    name: str
    languages: list[str]


class AdvisoryListResponse(BaseModel):
    count: int
    items: list[AdvisorySummary]


# ---------------------------------------------------------------------------
# Field reports
# ---------------------------------------------------------------------------
class FieldReportCreate(BaseModel):
    reporter_role: Literal["farmer", "extension", "expert"] = "farmer"
    reporter_name: str | None = None
    location_name: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    crop: str | None = None
    crop_stage: str | None = None
    observed_class: str | None = None
    severity: Literal["low", "medium", "high", "severe"] = "medium"
    notes: str | None = None


class FieldReportItem(BaseModel):
    id: int
    reporter_role: str
    reporter_name: str | None = None
    location_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    crop: str | None = None
    crop_stage: str | None = None
    observed_class: str | None = None
    severity: str
    notes: str | None = None
    status: str
    created_at: datetime
    review_count: int = 0


class FieldReportListResponse(BaseModel):
    total: int
    items: list[FieldReportItem]


# ---------------------------------------------------------------------------
# Expert reviews
# ---------------------------------------------------------------------------
class ReviewCreate(BaseModel):
    scan_id: int | None = None
    field_report_id: int | None = None
    reviewer_name: str | None = None
    verdict: Literal["confirmed", "rejected", "needs_lab"]
    corrected_class: str | None = None
    note: str | None = None


class ReviewItem(BaseModel):
    id: int
    scan_id: int | None = None
    field_report_id: int | None = None
    reviewer_name: str | None = None
    verdict: str
    corrected_class: str | None = None
    note: str | None = None
    created_at: datetime


class PendingReviewItem(BaseModel):
    """A scan in the validation queue (or a field report awaiting review)."""

    scan: ScanSummary
    prior_reviews: list[ReviewItem] = []


class PendingReviewListResponse(BaseModel):
    total: int
    items: list[PendingReviewItem]


# ---------------------------------------------------------------------------
# Hotspots + dashboard stats
# ---------------------------------------------------------------------------
class HotspotCell(BaseModel):
    lat_cell: int
    lon_cell: int
    center_lat: float
    center_lon: float
    total: int
    affected: int
    top_target: str | None = None
    reports: int = 0


class HotspotResponse(BaseModel):
    cell_degrees: float
    days: int
    cells: list[HotspotCell]


class TrendPoint(BaseModel):
    date: str
    total: int
    affected: int


class StatsResponse(BaseModel):
    total_scans: int
    affected_scans: int
    total_reports: int
    open_reports: int
    confirmed_detections: int
    rejected_reviews: int
    needs_lab_reviews: int
    top_targets: list[dict]
    trend_14d: list[TrendPoint]


# ---------------------------------------------------------------------------
# ORM -> schema helpers
# ---------------------------------------------------------------------------
def _urls(scan_id: int) -> tuple[str, str | None]:
    return f"/api/scans/{scan_id}/image", f"/api/scans/{scan_id}/annotated"


def review_item(review: ExpertReview) -> ReviewItem:
    return ReviewItem(
        id=review.id,
        scan_id=review.scan_id,
        field_report_id=review.field_report_id,
        reviewer_name=review.reviewer_name,
        verdict=review.verdict,
        corrected_class=review.corrected_class,
        note=review.note,
        created_at=review.created_at,
    )


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
        latitude=scan.latitude,
        longitude=scan.longitude,
        location_name=scan.location_name,
        crop=scan.crop,
        crop_stage=scan.crop_stage,
    )


def report_item(report: FieldReport) -> FieldReportItem:
    return FieldReportItem(
        id=report.id,
        reporter_role=report.reporter_role,
        reporter_name=report.reporter_name,
        location_name=report.location_name,
        latitude=report.latitude,
        longitude=report.longitude,
        crop=report.crop,
        crop_stage=report.crop_stage,
        observed_class=report.observed_class,
        severity=report.severity,
        notes=report.notes,
        status=report.status,
        created_at=report.created_at,
        review_count=len(report.reviews),
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
        latitude=scan.latitude,
        longitude=scan.longitude,
        location_name=scan.location_name,
        crop=scan.crop,
        crop_stage=scan.crop_stage,
    )
