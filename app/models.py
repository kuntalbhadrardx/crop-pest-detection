"""SQLAlchemy ORM models for the scan history."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    detections: Mapped[list[Detection]] = relationship(
        back_populates="scan",
        cascade="all, delete-orphan",
        lazy="selectin",  # batch-load detections with their scans
        order_by="Detection.id",
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
