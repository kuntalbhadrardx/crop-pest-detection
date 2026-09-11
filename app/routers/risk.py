"""Weather-based pest risk forecasting endpoint."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import FieldReport, Scan
from ..schemas import RiskResponse
from ..services.geo import haversine_km
from ..services.risk import evaluate, load_rules
from ..services.weather import get_weather

router = APIRouter(prefix="/api", tags=["risk"])


@router.get(
    "/risk",
    response_model=RiskResponse,
    summary="Weather-based pest risk forecast for a location",
    description=(
        "Resolves the location (village name or lat/lon), fetches the forecast "
        "(cached on disk for offline resilience), applies the pest rules from "
        "data/pest_rules.json plus recent affected scans/reports within the "
        "configured radius, and returns per-pest risk levels."
    ),
)
def get_risk(
    location: str | None = Query(None, description="Village/town name"),
    lat: float | None = Query(None, ge=-90, le=90),
    lon: float | None = Query(None, ge=-180, le=180),
    crop: str | None = Query(None, description="Crop name, e.g. rice, tomato"),
    crop_stage: str | None = Query(
        None, description="Growth stage: seedling/vegetative/flowering/fruiting/panicle/..."
    ),
    days: int = Query(7, ge=1, le=14, description="Forecast window (risk uses first 3 days)"),
    db: Session = Depends(get_db),
) -> RiskResponse:
    if not location and (lat is None or lon is None):
        raise HTTPException(
            status_code=422,
            detail="Provide ?location=<name> or both ?lat= and ?lon=",
        )

    weather = get_weather(location=location, lat=lat, lon=lon, days=days)
    if weather is None:
        detail = (
            f"Could not resolve location {location!r}."
            if location
            else "Weather provider unreachable and no cached forecast exists. "
            "Risk forecasting needs one successful online fetch per location "
            "(cached for 24 h) or a configured offline provider."
        )
        raise HTTPException(status_code=503, detail=detail)

    # Local outbreak signal: affected scans/reports within the rules radius.
    rules = load_rules()
    history_cfg = rules.get("history", {})
    radius_km = float(history_cfg.get("radius_km", 25))
    window_start = weather.get("daily", [{}])[0].get("date")

    since = None
    if window_start:
        try:
            from datetime import date as _date

            since = _date.fromisoformat(window_start) - timedelta(
                days=int(history_cfg.get("days", 14))
            )
        except ValueError:
            since = None

    center_lat, center_lon = float(weather["latitude"]), float(weather["longitude"])
    nearby = 0

    scan_rows = (
        db.query(Scan)
        .filter(Scan.status == "affected", Scan.latitude.isnot(None))
        .all()
    )
    for s in scan_rows:
        if since and s.created_at and s.created_at.date() < since:
            continue
        if haversine_km(center_lat, center_lon, s.latitude, s.longitude) <= radius_km:
            nearby += 1

    report_rows = (
        db.query(FieldReport)
        .filter(FieldReport.severity.in_(("high", "severe")), FieldReport.latitude.isnot(None))
        .all()
    )
    for r in report_rows:
        if since and r.created_at and r.created_at.date() < since:
            continue
        if haversine_km(center_lat, center_lon, r.latitude, r.longitude) <= radius_km:
            nearby += 1

    result = evaluate(weather, crop=crop, crop_stage=crop_stage, nearby_affected=nearby)

    return RiskResponse(
        location=weather.get("location") or location,
        latitude=center_lat,
        longitude=center_lon,
        crop=crop,
        crop_stage=crop_stage,
        overall_level=result["overall_level"],
        per_pest=result["per_pest"],
        weather_summary=result["weather_summary"],
        history_driver=result["history_driver"],
        weather_stale=result["weather_stale"],
    )
