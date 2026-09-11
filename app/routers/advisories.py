"""Multilingual advisory endpoints."""
from fastapi import APIRouter, Query

from ..schemas import (
    AdvisoryListResponse,
    AdvisoryResponse,
    AdvisorySummary,
    LanguagesResponse,
)
from ..services import advisory

router = APIRouter(prefix="/api", tags=["advisories"])


@router.get(
    "/languages",
    response_model=LanguagesResponse,
    summary="Languages advisories are available in",
)
def list_languages() -> LanguagesResponse:
    langs = advisory.languages()
    return LanguagesResponse(
        count=len(langs),
        default=advisory.default_language(),
        languages=langs,
    )


@router.get(
    "/advisories",
    response_model=AdvisoryListResponse,
    summary="List all advisory targets (pests/diseases with guidance)",
)
def list_advisories() -> AdvisoryListResponse:
    data = advisory.load_advisories()
    items = []
    for key in advisory.targets():
        entry = data["targets"][key]
        name = (entry.get(advisory.default_language()) or {}).get("name", key)
        langs = sorted(entry.keys() & {"en", "hi", "mr", "ta", "te"})
        items.append(AdvisorySummary(target=key, name=name, languages=langs))
    return AdvisoryListResponse(count=len(items), items=items)


@router.get(
    "/advisory",
    response_model=AdvisoryResponse,
    summary="Localized advisory for one pest/disease",
    description=(
        "IPM management steps, safe pesticide-use guidance and follow-up in the "
        "requested language (en/hi/mr/ta/te). Pass confidence/risk_level to "
        "trigger the expert-referral block when uncertain or severe."
    ),
)
def get_advisory(
    class_name: str = Query(..., description="Pest/disease class, e.g. rice_blast"),
    lang: str | None = Query(None, description="Language code: en, hi, mr, ta, te"),
    confidence: float | None = Query(None, ge=0, le=1),
    risk_level: str | None = Query(None),
) -> AdvisoryResponse:
    result = advisory.get_advisory(
        class_name, lang=lang, confidence=confidence, risk_level=risk_level
    )
    if result is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=404,
            detail=f"No advisory content for {class_name!r}. Known targets: {advisory.targets()}",
        )
    return AdvisoryResponse(**result)
