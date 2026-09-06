"""Image upload + detection endpoint."""
import io
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from PIL import Image
from sqlalchemy.orm import Session

from ..config import BASE_DIR, settings
from ..database import get_db
from ..detector import Detector
from ..models import Detection as DetectionRow
from ..models import Scan
from ..schemas import ScanDetail, detail_from_scan

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["detection"])

_EXTENSIONS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "BMP": "bmp", "TIFF": "tif"}


def _rel(path: Path) -> str:
    """Store paths relative to the project root so scans survive directory moves."""
    try:
        return path.relative_to(BASE_DIR).as_posix()
    except ValueError:
        return str(path)


def _display_name(original_name: str | None) -> str:
    name = Path(original_name or "").name.strip() or "image"
    return name[:255]


def _store_upload(data: bytes, original_name: str | None) -> Path:
    """Validate the bytes are a decodable image and persist them; else 400."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
        fmt = Image.open(io.BytesIO(data)).format
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is not a valid image (JPEG/PNG/WEBP/BMP/TIFF).",
        )

    extension = _EXTENSIONS.get(fmt or "")
    if extension is None:
        raise HTTPException(status_code=400, detail=f"Unsupported image format: {fmt!r}")

    originals = settings.upload_dir / "originals"
    originals.mkdir(parents=True, exist_ok=True)
    path = originals / f"{uuid.uuid4().hex}.{extension}"
    path.write_bytes(data)
    return path


@router.post(
    "/detect",
    response_model=ScanDetail,
    status_code=201,
    summary="Detect pests/diseases in an uploaded crop image",
    description=(
        "Accepts a JPEG/PNG/WEBP/BMP/TIFF image, runs the loaded YOLO model, "
        "stores the scan (with every detection) in the history, and returns "
        "bounding boxes in pixel coordinates."
    ),
)
def detect_image(
    request: Request,
    db: Session = Depends(get_db),
    file: UploadFile = File(..., description="Crop image file"),
) -> ScanDetail:
    detector: Detector = request.app.state.detector
    if not detector.available:
        raise HTTPException(
            status_code=503,
            detail=f"Model is not loaded. Reason: {detector.error}",
        )

    # Stream the upload in chunks and enforce the size limit.
    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = b""
    while chunk := file.file.read(1024 * 1024):
        data += chunk
        if len(data) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Image exceeds the {settings.max_upload_mb} MB limit.",
            )

    original = _store_upload(data, file.filename)
    annotated = settings.upload_dir / "annotated" / f"{original.stem}_annotated.jpg"

    try:
        result = detector.predict(image_path=original, annotated_path=annotated)
    except Exception as exc:
        logger.exception("Inference failed for %s", original)
        original.unlink(missing_ok=True)
        annotated.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Inference failed: {exc}")

    detections = result["detections"]
    status = "affected" if any(
        d["class_name"] not in settings.healthy_classes for d in detections
    ) else "healthy"

    scan = Scan(
        filename=_display_name(file.filename),
        status=status,
        model_version=detector.model_version or "unknown",
        image_path=_rel(original),
        annotated_path=_rel(annotated) if result["annotated_path"] else None,
        image_width=result["image_width"],
        image_height=result["image_height"],
    )
    for d in detections:
        scan.detections.append(
            DetectionRow(
                class_name=d["class_name"],
                confidence=d["confidence"],
                bbox_x=d["bbox"]["x"],
                bbox_y=d["bbox"]["y"],
                bbox_w=d["bbox"]["width"],
                bbox_h=d["bbox"]["height"],
            )
        )

    db.add(scan)
    db.commit()
    logger.info(
        "Scan %d stored: %s (%d detection(s), status=%s)",
        scan.id,
        scan.filename,
        len(detections),
        status,
    )
    return detail_from_scan(scan)
