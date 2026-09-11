"""Field report endpoints — farmer/extension observations."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import FieldReport
from ..schemas import FieldReportCreate, FieldReportItem, FieldReportListResponse, report_item

router = APIRouter(prefix="/api", tags=["reports"])


@router.post(
    "/reports",
    response_model=FieldReportItem,
    status_code=201,
    summary="Submit a field observation (farmer or extension worker)",
)
def create_report(payload: FieldReportCreate, db: Session = Depends(get_db)) -> FieldReportItem:
    report = FieldReport(
        reporter_role=payload.reporter_role,
        reporter_name=(payload.reporter_name or "")[:255] or None,
        latitude=payload.latitude,
        longitude=payload.longitude,
        location_name=(payload.location_name or "")[:255] or None,
        crop=(payload.crop or "")[:100] or None,
        crop_stage=(payload.crop_stage or "")[:50] or None,
        observed_class=(payload.observed_class or "")[:100] or None,
        severity=payload.severity,
        notes=payload.notes,
    )
    db.add(report)
    db.commit()
    return report_item(report)


@router.get(
    "/reports",
    response_model=FieldReportListResponse,
    summary="List field reports (newest first, paginated)",
)
def list_reports(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> FieldReportListResponse:
    total = db.scalar(func.count(FieldReport.id)) or 0
    rows = (
        db.query(FieldReport)
        .order_by(FieldReport.created_at.desc(), FieldReport.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return FieldReportListResponse(total=total, items=[report_item(r) for r in rows])
