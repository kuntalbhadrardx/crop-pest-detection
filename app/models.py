"""SQLAlchemy ORM models for the scan history."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Scan(Base):
    """One uploaded image that went through detection."""

    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(20), default="healthy")  # healthy | affected
    model_version: Mapped[str] = mapped_column(String(255), default="")
    image_path: Mapped[str] = mapped_column(String(1024), default="")
    annotated_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    image_width: Mapped[int] = mapped_column(Integer, default=0)
    image_height: Mapped[int] = mapped_column(Integer, default=0)
    # Field context (all optional — filled when the submitter provides it).
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    crop: Mapped[str | None] = mapped_column(String(100), nullable=True)
    crop_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    detections: Mapped[list[Detection]] = relationship(
        back_populates="scan",
        cascade="all, delete-orphan",
        lazy="selectin",  # batch-load detections with their scans
        order_by="Detection.id",
    )
    reviews: Mapped[list[ExpertReview]] = relationship(
        back_populates="scan",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ExpertReview.id",
    )


class Detection(Base):
    """A single object detected inside a scan."""

    __tablename__ = "detections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scan_id: Mapped[int] = mapped_column(
        ForeignKey("scans.id", ondelete="CASCADE"), index=True
    )
    class_name: Mapped[str] = mapped_column(String(100))
    confidence: Mapped[float] = mapped_column(Float)
    # Top-left corner + size in pixels of the original image.
    bbox_x: Mapped[float] = mapped_column(Float)
    bbox_y: Mapped[float] = mapped_column(Float)
    bbox_w: Mapped[float] = mapped_column(Float)
    bbox_h: Mapped[float] = mapped_column(Float)

    scan: Mapped[Scan] = relationship(back_populates="detections")


class FieldReport(Base):
    """A farmer/extension field observation (no model inference required)."""

    __tablename__ = "field_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reporter_role: Mapped[str] = mapped_column(String(20), default="farmer")  # farmer | extension | expert
    reporter_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    crop: Mapped[str | None] = mapped_column(String(100), nullable=True)
    crop_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    observed_class: Mapped[str | None] = mapped_column(String(100), nullable=True)
    severity: Mapped[str] = mapped_column(String(20), default="medium")  # low | medium | high | severe
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | reviewed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    reviews: Mapped[list[ExpertReview]] = relationship(
        back_populates="field_report",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ExpertReview(Base):
    """Expert verdict on a scan or a field report (the learning loop)."""

    __tablename__ = "expert_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scan_id: Mapped[int | None] = mapped_column(
        ForeignKey("scans.id", ondelete="CASCADE"), nullable=True, index=True
    )
    field_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("field_reports.id", ondelete="CASCADE"), nullable=True, index=True
    )
    reviewer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    verdict: Mapped[str] = mapped_column(String(20))  # confirmed | rejected | needs_lab
    corrected_class: Mapped[str | None] = mapped_column(String(100), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    scan: Mapped[Scan | None] = relationship(back_populates="reviews")
    field_report: Mapped[FieldReport | None] = relationship(back_populates="reviews")
