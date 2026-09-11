"""Offline-first support for the PWA / Android app.

``GET /api/offline/bundle`` returns everything the client needs to work with
no internet and no server:

* the full multilingual advisory library (en/hi/mr/ta/te),
* the weather→pest risk rules (so the phone can score risk itself),
* referral thresholds and metadata.

The response is explicitly cacheable (``Cache-Control: public, max-age=86400``
with 7-day stale-while-revalidate) so devices download it at most once a day.
Client version negotiation via ``?v=<their version>`` returns **304 Not
Modified** when the bundle is unchanged — a few hundred bytes instead of 60 KB
on every daily refresh.
"""
from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter, Query, Request, Response

from ..services import advisory, risk

router = APIRouter(prefix="/api/offline", tags=["offline"])

_CACHE_CONTROL = "public, max-age=86400, stale-while-revalidate=604800"


def build_bundle() -> dict:
    """Assemble the offline bundle. Kept importable for tests."""
    rules = risk.load_rules()
    advisories = advisory.load_advisories()
    return {
        "version": str(rules.get("version", 1)) + "-" + str(advisories.get("version", 1)),
        "generated_from": {
            "pest_rules": "data/pest_rules.json",
            "advisories": "data/advisories.json",
        },
        "advisories": {
            "languages": advisories.get("languages", ["en"]),
            "default_language": advisories.get("default_language", "en"),
            "referral_threshold": advisories.get("referral_threshold", 0.5),
            "referral": advisories.get("referral", {}),
            "targets": advisories.get("targets", {}),
        },
        "risk_rules": rules,
    }


@router.get("/bundle", summary="Everything the mobile app needs to run offline")
def offline_bundle(
    request: Request,
    v: str | None = Query(default=None, description="Client's current bundle version"),
) -> Response:
    bundle = build_bundle()
    etag = '"' + hashlib.sha1(
        json.dumps(bundle, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16] + '"'

    headers = {
        "Cache-Control": _CACHE_CONTROL,
        "ETag": etag,
    }
    # Fast client-side version check: no download when unchanged.
    if v is not None and f'"{v}"' == etag:
        return Response(status_code=304, headers=headers)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)

    body = json.dumps(bundle, ensure_ascii=False)
    return Response(
        content=body,
        media_type="application/json; charset=utf-8",
        headers=headers,
    )
