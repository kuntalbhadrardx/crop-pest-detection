"""Geospatial hotspots + officials dashboard statistics."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Detection, ExpertReview, FieldReport, Scan
from ..schemas import (
    HotspotCell,
    HotspotResponse,
    StatsResponse,
    TrendPoint,
)

router = APIRouter(prefix="/api", tags=["insights"])

CELL_DEGREES = 0.25  # ~27 km grid cells for hotspot clustering


def _cell_of(lat: float, lon: float) -> tuple[int, int]:
    return int(lat // CELL_DEGREES), int(lon // CELL_DEGREES)


@router.get(
    "/hotspots",
    response_model=HotspotResponse,
    summary="Geospatial hotspots — clustered scans + reports by grid cell",
    description=(
        "Clusters located scans and high-severity field reports into ~27 km grid "
        "cells and ranks them by affected share. Feed the cells to a map for the "
        "officials' hotspot view."
    ),
)
def get_hotspots(
    days: int = Query(7, ge=1, le=90, description="Look-back window"),
    db: Session = Depends(get_db),
) -> HotspotResponse:
    since = datetime.now(timezone.utc) - timedelta(days=days)

    cells: dict[tuple[int, int], dict] = {}

    scan_rows = (
        db.query(Scan)
        .filter(Scan.created_at >= since, Scan.latitude.isnot(None))
        .all()
    )
    for s in scan_rows:
        key = _cell_of(s.latitude, s.longitude)
        cell = cells.setdefault(
            key,
            {
                "lat_cell": key[0],
                "lon_cell": key[1],
                "sum_lat": 0.0,
                "sum_lon": 0.0,
                "n": 0,
                "affected": 0,
                "reports": 0,
                "targets": {},
            },
        )
        cell["sum_lat"] += s.latitude
        cell["sum_lon"] += s.longitude
        cell["n"] += 1
        if s.status == "affected":
            cell["affected"] += 1
            for d in s.detections:
                cell["targets"][d.class_name] = cell["targets"].get(d.class_name, 0) + 1

    report_rows = (
        db.query(FieldReport)
        .filter(
            FieldReport.created_at >= since,
            FieldReport.latitude.isnot(None),
            FieldReport.severity.in_(("high", "severe")),
        )
        .all()
    )
    for r in report_rows:
        key = _cell_of(r.latitude, r.longitude)
        cell = cells.setdefault(
            key,
            {
                "lat_cell": key[0],
                "lon_cell": key[1],
                "sum_lat": 0.0,
                "sum_lon": 0.0,
                "n": 0,
                "affected": 0,
                "reports": 0,
                "targets": {},
            },
        )
        cell["sum_lat"] += r.latitude
        cell["sum_lon"] += r.longitude
        cell["n"] += 1
        cell["reports"] += 1
        if r.observed_class:
            cell["targets"][r.observed_class] = cell["targets"].get(r.observed_class, 0) + 1

    out = []
    for cell in cells.values():
        n = cell["n"]
        targets = sorted(cell["targets"].items(), key=lambda kv: kv[1], reverse=True)
        out.append(
            HotspotCell(
                lat_cell=cell["lat_cell"],
                lon_cell=cell["lon_cell"],
                center_lat=round(cell["sum_lat"] / n, 5),
                center_lon=round(cell["sum_lon"] / n, 5),
                total=n,
                affected=cell["affected"],
                top_target=targets[0][0] if targets else None,
                reports=cell["reports"],
            )
        )

    # Hottest first: most affected, then most reports, then biggest cluster.
    out.sort(key=lambda c: (c.affected, c.reports, c.total), reverse=True)
    return HotspotResponse(cell_degrees=CELL_DEGREES, days=days, cells=out)


@router.get(
    "/stats/summary",
    response_model=StatsResponse,
    summary="Dashboard statistics — totals, top pests, 14-day trend",
)
def get_stats(db: Session = Depends(get_db)) -> StatsResponse:
    total_scans = db.scalar(select(func.count(Scan.id))) or 0
    affected_scans = db.scalar(
        select(func.count(Scan.id)).where(Scan.status == "affected")
    ) or 0
    total_reports = db.scalar(select(func.count(FieldReport.id))) or 0
    open_reports = db.scalar(
        select(func.count(FieldReport.id)).where(FieldReport.status == "open")
    ) or 0

    verdict_counts = dict(
        db.query(ExpertReview.verdict, func.count(ExpertReview.id))
        .group_by(ExpertReview.verdict)
        .all()
    )

    top = (
        db.query(
            Detection.class_name.label("target"),
            func.count(Detection.id).label("hits"),
            func.avg(Detection.confidence).label("avg_conf"),
        )
        .join(Scan, Scan.id == Detection.scan_id)
        .filter(Scan.status == "affected")
        .group_by(Detection.class_name)
        .order_by(func.count(Detection.id).desc())
        .limit(10)
        .all()
    )
    top_targets = [
        {"target": t.target, "hits": t.hits, "avg_confidence": round(float(t.avg_conf or 0), 3)}
        for t in top
    ]

    since = date.today() - timedelta(days=13)
    trend_rows = (
        db.query(func.date(Scan.created_at).label("day"), func.count(Scan.id))
        .filter(Scan.created_at >= since)
        .group_by(func.date(Scan.created_at))
        .all()
    )
    per_day_total = {str(day): n for day, n in trend_rows}
    affected_rows = (
        db.query(func.date(Scan.created_at).label("day"), func.count(Scan.id))
        .filter(Scan.created_at >= since, Scan.status == "affected")
        .group_by(func.date(Scan.created_at))
        .all()
    )
    per_day_affected = {str(day): n for day, n in affected_rows}

    trend = []
    for i in range(14):
        day = (since + timedelta(days=i)).isoformat()
        trend.append(
            TrendPoint(
                date=day,
                total=per_day_total.get(day, 0),
                affected=per_day_affected.get(day, 0),
            )
        )

    return StatsResponse(
        total_scans=total_scans,
        affected_scans=affected_scans,
        total_reports=total_reports,
        open_reports=open_reports,
        confirmed_detections=verdict_counts.get("confirmed", 0),
        rejected_reviews=verdict_counts.get("rejected", 0),
        needs_lab_reviews=verdict_counts.get("needs_lab", 0),
        top_targets=top_targets,
        trend_14d=trend,
    )
