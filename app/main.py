"""Crop Pest & Disease Detection API — FastAPI entry point.

Run from the project root:
    uvicorn app.main:app --reload
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import BASE_DIR, settings
from .database import init_db
from .detector import Detector

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    detector = Detector(settings)
    app.state.detector = detector
    if detector.available:
        source = "pretrained fallback" if detector.is_fallback else "custom weights"
        logger.info(
            "YOLO model ready: %s (%s) on %s — %d classes",
            detector.model_version,
            source,
            detector.device,
            len(detector.names),
        )
    else:
        logger.warning(
            "YOLO model NOT loaded — /api/detect will return 503. Reason: %s",
            detector.error,
        )
    yield


app = FastAPI(
    title="Crop Pest & Disease Detection API",
    description=(
        "Upload crop images to detect pests/diseases with a YOLO model, "
        "then browse the stored scan history."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,  # must stay False when allow_origins=["*"]
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Imported after app creation to avoid circular imports.
from .routers import (  # noqa: E402
    advisories,
    detect,
    insights,
    info,
    offline,
    reports,
    reviews,
    risk,
    scans,
)

app.include_router(detect.router)
app.include_router(scans.router)
app.include_router(info.router)
app.include_router(risk.router)
app.include_router(advisories.router)
app.include_router(reports.router)
app.include_router(reviews.router)
app.include_router(insights.router)
app.include_router(offline.router)

# Serve the upload UI at the root. Routers above are registered first, so all
# /api, /docs and /openapi.json routes keep precedence over this catch-all.
app.mount("/", StaticFiles(directory=str(BASE_DIR / "static"), html=True), name="ui")
