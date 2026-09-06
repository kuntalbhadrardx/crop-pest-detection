"""Model/service info endpoints."""
from fastapi import APIRouter, HTTPException, Request

from ..detector import Detector
from ..schemas import ClassInfo, ClassesResponse, HealthResponse

router = APIRouter(prefix="/api", tags=["info"])


def _detector(request: Request) -> Detector:
    return request.app.state.detector


@router.get("/health", response_model=HealthResponse, summary="Model + service health")
def health(request: Request) -> HealthResponse:
    det = _detector(request)
    return HealthResponse(
        status="ok" if det.available else "degraded",
        model_loaded=det.available,
        model_version=det.model_version,
        fallback_in_use=det.is_fallback,
        device=det.device if det.available else None,
        class_count=len(det.names) if det.available else None,
        error=det.error,
    )


@router.get("/classes", response_model=ClassesResponse, summary="Classes the loaded model detects")
def classes(request: Request) -> ClassesResponse:
    det = _detector(request)
    if not det.available:
        raise HTTPException(status_code=503, detail=f"Model is not loaded: {det.error}")
    items = [ClassInfo(id=cls_id, name=name) for cls_id, name in det.names_map.items()]
    return ClassesResponse(count=len(items), classes=items)
