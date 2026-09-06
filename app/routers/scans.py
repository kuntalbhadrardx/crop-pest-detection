"""Scan history + image-serving endpoints."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import BASE_DIR
from ..database import get_db
from ..models import Scan
from ..schemas import ScanDetail, ScanListResponse, detail_from_scan, summary_from_scan

router = APIRouter(prefix="/api", tags=["scans"])


def _resolve(path_str: str) -> Path:
    p = Path(path_str)
    return p if p.is_absolute() else BASE_DIR / p


def _get_scan_or_404(scan_id: int, db: Session) -> Scan:
    scan = db.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail=f"No scan with id {scan_id}")
    return scan


@router.get(
    "/scans",
    response_model=ScanListResponse,
    summary="List scan history (newest first, paginated)",
)
def list_scans(
    skip: int = Query(0, ge=0, description="Items to skip"),
    limit: int = Query(20, ge=1, le=100, description="Max items to return"),
    db: Session = Depends(get_db),
) -> ScanListResponse:
    total = db.scalar(func.count(Scan.id)) or 0
    rows = (
        db.query(Scan)
        .order_by(Scan.created_at.desc(), Scan.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return ScanListResponse(total=total, items=[summary_from_scan(s) for s in rows])


@router.get("/scans/{scan_id}", response_model=ScanDetail, summary="Scan detail with detections")
def get_scan(scan_id: int, db: Session = Depends(get_db)) -> ScanDetail:
    return detail_from_scan(_get_scan_or_404(scan_id, db))


@router.get("/scans/{scan_id}/image", summary="Original uploaded image")
def get_original_image(scan_id: int, db: Session = Depends(get_db)) -> FileResponse:
    scan = _get_scan_or_404(scan_id, db)
    path = _resolve(scan.image_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Image file is missing on disk")
    return FileResponse(path)


@router.get("/scans/{scan_id}/annotated", summary="Image with YOLO detections drawn")
def get_annotated_image(scan_id: int, db: Session = Depends(get_db)) -> FileResponse:
    scan = _get_scan_or_404(scan_id, db)
    if not scan.annotated_path:
        raise HTTPException(status_code=404, detail="No annotated image stored for this scan")
    path = _resolve(scan.annotated_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Annotated image file is missing on disk")
    return FileResponse(path)
