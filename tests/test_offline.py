"""Tests for offline/Android (PWA) support.

Covers the /api/offline/bundle endpoint (advisories + rules in one cacheable
payload with ETag revalidation), the upgraded app shell (manifest, service
worker, installable page), and scan integrity for the offline sync replay.
"""
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import main as main_module
from app.main import app

ROOT = Path(__file__).resolve().parent.parent


class FakeDetector:
    """Same deterministic stub as the other test modules."""

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


# ---------------------------------------------------------------------------
# /api/offline/bundle
# ---------------------------------------------------------------------------
def test_bundle_contains_advisories_and_rules(client):
    resp = client.get("/api/offline/bundle")
    assert resp.status_code == 200
    body = resp.json()

    # Advisories: languages + full multilingual target content.
    adv = body["advisories"]
    assert set(["en", "hi", "mr", "ta", "te"]).issubset(set(adv["languages"]))
    assert adv["default_language"] == "en"
    assert "rice_blast" in adv["targets"]
    blast = adv["targets"]["rice_blast"]
    for lang in ("en", "hi", "mr", "ta", "te"):
        assert blast[lang]["management"], f"missing management steps for {lang}"
    assert adv["referral"]["en"]["text"]

    # Risk rules: rule list with conditions the client can evaluate.
    rules = body["risk_rules"]
    assert rules["rules"], "no risk rules in bundle"
    rule = rules["rules"][0]
    assert {"id", "target", "weight", "conditions"} <= set(rule.keys())


def test_bundle_cache_headers_and_etag(client):
    resp = client.get("/api/offline/bundle")
    assert resp.status_code == 200
    assert "max-age" in resp.headers["cache-control"]
    etag = resp.headers["etag"]
    assert etag.startswith('"')

    # Conditional request with matching ETag -> 304 (no body to re-download).
    revalid = client.get("/api/offline/bundle", headers={"if-none-match": etag})
    assert revalid.status_code == 304
    assert not revalid.content

    # Explicit ?v= version check (the PWA's cheap daily refresh) -> 304.
    vcheck = client.get("/api/offline/bundle", params={"v": etag.strip('"')})
    assert vcheck.status_code == 304

    # Changed version -> full payload again.
    fresh = client.get("/api/offline/bundle", params={"v": "old-version"})
    assert fresh.status_code == 200
    assert fresh.json()["advisories"]["targets"]


def test_bundle_version_is_stable(client):
    v1 = client.get("/api/offline/bundle").json()["version"]
    v2 = client.get("/api/offline/bundle").json()["version"]
    assert v1 == v2


# ---------------------------------------------------------------------------
# App shell: manifest, service worker, installable page
# ---------------------------------------------------------------------------
def test_manifest_is_served_and_installable(client):
    resp = client.get("/manifest.webmanifest")
    assert resp.status_code == 200
    manifest = resp.json()
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "/"
    assert manifest["icons"], "PWA needs at least one icon"


def test_service_worker_and_offline_page_served(client):
    sw = client.get("/sw.js")
    assert sw.status_code == 200
    assert "sync-scans" in sw.text  # background sync queue registered
    offline = client.get("/offline.html")
    assert offline.status_code == 200


def test_index_registers_pwa_and_offline_ui(client):
    html = client.get("/").text
    assert 'rel="manifest"' in html
    assert "serviceWorker" in html
    assert "Waiting to sync" in html
    assert "capture=\"environment\"" in html  # native camera on Android


# ---------------------------------------------------------------------------
# Scan replay integrity: the SW replays a queued scan as a plain multipart
# POST /api/detect — it must behave exactly like a normal online scan.
# ---------------------------------------------------------------------------
def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), "green").save(buf, "PNG")
    return buf.getvalue()


def test_detect_accepts_replayed_multipart_fields(client):
    """Fields the SW queue appends on replay are all accepted."""
    resp = client.post(
        "/api/detect",
        files={"file": ("queued.jpg", _png_bytes(), "image/jpeg")},
        data={
            "location_name": "Field 12",
            "latitude": "17.38",
            "longitude": "78.48",
            "crop": "rice",
            "crop_stage": "tillering",
        },
    )
    assert resp.status_code in (200, 201)  # detect returns 201 Created
    body = resp.json()
    assert body["status"] == "affected"
    assert body["detections"][0]["class_name"] == "rice_blast"
    assert body["location_name"] == "Field 12"
    assert body["crop"] == "rice"
    assert body["crop_stage"] == "tillering"
    assert body["latitude"] == pytest.approx(17.38)


def test_detect_replay_without_optional_fields(client):
    """A bare replay (photo only, no context) still works."""
    resp = client.post(
        "/api/detect",
        files={"file": ("queued.jpg", _png_bytes(), "image/jpeg")},
    )
    assert resp.status_code in (200, 201)
    assert resp.json()["status"] == "affected"
