"""Expert validation endpoints — the human-in-the-loop learning system."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from ..database import get_db
from ..models import ExpertReview, FieldReport, Scan
from ..schemas import (
    PendingReviewItem,
    PendingReviewListResponse,
    ReviewCreate,
    ReviewItem,
    summary_from_scan,
    review_item,
)

router = APIRouter(prefix="/api", tags=["reviews"])


@router.post(
    "/reviews",
    response_model=ReviewItem,
    status_code=201,
    summary="Record an expert verdict on a scan or field report",
    description=(
        "Verdicts: confirmed (detection correct), rejected (false alarm) or "
        "needs_lab (refer to laboratory). Confirmed/rejected reviews feed the "
        "training-data export (scripts/export_training.py)."
    ),
)
def create_review(payload: ReviewCreate, db: Session = Depends(get_db)) -> ReviewItem:
    if bool(payload.scan_id) == bool(payload.field_report_id):
        raise HTTPException(
            status_code=422, detail="Provide exactly one of scan_id or field_report_id"
        )

    if payload.scan_id is not None:
        if db.get(Scan, payload.scan_id) is None:
            raise HTTPException(status_code=404, detail=f"No scan with id {payload.scan_id}")
    elif db.get(FieldReport, payload.field_report_id) is None:
        raise HTTPException(
            status_code=404, detail=f"No field report with id {payload.field_report_id}"
        )

    review = ExpertReview(
        scan_id=payload.scan_id,
        field_report_id=payload.field_report_id,
        reviewer_name=(payload.reviewer_name or "")[:255] or None,
        verdict=payload.verdict,
        corrected_class=(payload.corrected_class or "")[:100] or None,
        note=payload.note,
    )
    if payload.field_report_id is not None:
        report = db.get(FieldReport, payload.field_report_id)
        report.status = "reviewed"

    db.add(review)
    db.commit()
    return review_item(review)


@router.get(
    "/reviews",
    response_model=list[ReviewItem],
    summary="Recent expert reviews (newest first)",
)
def list_reviews(
    limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)
) -> list[ReviewItem]:
    rows = (
        db.query(ExpertReview)
        .order_by(ExpertReview.created_at.desc(), ExpertReview.id.desc())
        .limit(limit)
        .all()
    )
    return [review_item(r) for r in rows]


@router.get(
    "/reviews/pending",
    response_model=PendingReviewListResponse,
    summary="Validation queue — scans without an expert verdict",
)
def pending_reviews(
    limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)
) -> PendingReviewListResponse:
    rows = (
        db.query(Scan)
        .outerjoin(ExpertReview, ExpertReview.scan_id == Scan.id)
        .filter(ExpertReview.id.is_(None))
        .options(joinedload(Scan.detections))
        .order_by(Scan.created_at.desc(), Scan.id.desc())
        .limit(limit)
        .all()
    )
    items = [PendingReviewItem(scan=summary_from_scan(s)) for s in rows]
    return PendingReviewListResponse(total=len(items), items=items)
