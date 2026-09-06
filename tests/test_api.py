"""API tests using a stubbed detector (no ultralytics/PyTorch required)."""
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import main as main_module
from app.main import app

ROOT = Path(__file__).resolve().parent.parent


class FakeDetector:
    """Stands in for app.detector.Detector; returns deterministic results."""

    def __init__(self, settings):
        self.model = object()
        self.model_version = "fake.pt"
        self.is_fallback = False
        self.device = "cpu"
        self.error = None
        self.names = ["rice_blast", "healthy"]

    @property
    def available(self):
        return True

    @property
    def names_map(self):
        return {0: "rice_blast", 1: "healthy"}

    def predict(self, image_path, annotated_path=None):
        detections = [
            {
                "class_name": "rice_blast",
                "confidence": 0.91,
                "bbox": {"x": 10.0, "y": 20.0, "width": 100.0, "height": 80.0},
            }
        ]
        annotated = None
        if annotated_path is not None:
            annotated_path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (320, 240), "green").save(annotated_path, "JPEG")
            annotated = str(annotated_path)
        return {
            "detections": detections,
            "image_width": 320,
            "image_height": 240,
            "annotated_path": annotated,
        }


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(main_module, "Detector", FakeDetector)
    with TestClient(app) as test_client:
        yield test_client


def _png_bytes(color: str = "green", size: tuple[int, int] = (64, 48)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
def test_root_serves_ui(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Pest" in resp.text  # upload UI page
    assert "api/detect" in resp.text


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["model_loaded"] is True
    assert body["model_version"] == "fake.pt"
    assert body["device"] == "cpu"
    assert body["class_count"] == 2


def test_classes(client):
    resp = client.get("/api/classes")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    names = [c["name"] for c in body["classes"]]
    assert "rice_blast" in names


def test_detect_full_flow(client):
    post = client.post(
        "/api/detect",
        files={"file": ("leaf.png", _png_bytes(), "image/png")},
    )
    assert post.status_code == 201, post.text
    body = post.json()

    assert body["status"] == "affected"
    assert body["filename"] == "leaf.png"
    assert body["model_version"] == "fake.pt"
    assert body["image_width"] == 320 and body["image_height"] == 240
    assert body["detection_count"] == 1
    det = body["detections"][0]
    assert det["class_name"] == "rice_blast"
    assert det["confidence"] == 0.91
    assert det["bbox"]["width"] == 100.0
    assert body["image_url"] == f"/api/scans/{body['id']}/image"
    assert body["annotated_url"] == f"/api/scans/{body['id']}/annotated"
    scan_id = body["id"]

    # Detail endpoint
    detail = client.get(f"/api/scans/{scan_id}")
    assert detail.status_code == 200
    assert detail.json()["detections"][0]["bbox"]["x"] == 10.0

    # History list
    listing = client.get("/api/scans").json()
    assert listing["total"] >= 1
    assert listing["items"][0]["id"] == scan_id
    assert listing["items"][0]["status"] == "affected"

    # Served images
    original = client.get(f"/api/scans/{scan_id}/image")
    assert original.status_code == 200
    assert original.headers["content-type"].startswith("image/")

    annotated = client.get(f"/api/scans/{scan_id}/annotated")
    assert annotated.status_code == 200
    assert annotated.headers["content-type"].startswith("image/")


def test_detect_rejects_non_image(client):
    resp = client.post(
        "/api/detect",
        files={"file": ("notes.txt", b"not an image", "text/plain")},
    )
    assert resp.status_code == 400
    assert "not a valid image" in resp.json()["detail"]


def test_detect_rejects_oversized_upload(client):
    # 21 MB exceeds the 20 MB MAX_UPLOAD_MB default. The size check runs
    # before image validation, so the payload does not need to be a real PNG.
    big = b"x" * (21 * 1024 * 1024)
    resp = client.post(
        "/api/detect",
        files={"file": ("huge.png", big, "image/png")},
    )
    assert resp.status_code == 413


def test_unknown_scan_404(client):
    resp = client.get("/api/scans/999999")
    assert resp.status_code == 404
