"""Advisory lookup: localized IPM guidance from ``data/advisories.json``.

All content is a local JSON file (offline by design — no translation API).
Language codes: en, hi, mr, ta, te.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..config import BASE_DIR

ADVISORIES_PATH = BASE_DIR / "data" / "advisories.json"


@lru_cache(maxsize=1)
def load_advisories() -> dict:
    try:
        return json.loads(ADVISORIES_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"languages": ["en"], "default_language": "en", "targets": {}}


def languages() -> list[str]:
    return load_advisories().get("languages", ["en"])


def default_language() -> str:
    return load_advisories().get("default_language", "en")


def normalize_lang(lang: str | None) -> str:
    """Validate/normalize a language code against the content file."""
    available = languages()
    code = (lang or "").strip().lower()
    return code if code in available else default_language()


def targets() -> list[str]:
    return sorted(load_advisories().get("targets", {}).keys())


def _referral_needed(confidence: float | None, level: str | None) -> bool:
    data = load_advisories()
    if confidence is not None and confidence < float(data.get("referral_threshold", 0.5)):
        return True
    return level in ("severe",)


def get_advisory(
    class_name: str,
    lang: str | None = None,
    confidence: float | None = None,
    risk_level: str | None = None,
) -> dict | None:
    """Localized advisory for one pest/disease class.

    Args:
        class_name: model class (e.g. ``rice_blast``). Underscore/hyphen/space
            variants are normalized so ``"Rice Blast"`` also resolves.
        lang: language code (en/hi/mr/ta/te) — falls back to default.
        confidence: model confidence (0..1); below the threshold triggers the
            expert-referral block.
        risk_level: risk-engine level for the same target; ``severe`` triggers
            the expert-referral block.

    Returns:
        dict with ``target``, ``language``, ``name``, ``management``,
        ``safety``, ``followup_days``, ``referral`` (dict or None),
        ``available_languages`` — or None for unknown targets.
    """
    data = load_advisories()
    key = class_name.strip().lower().replace("-", "_").replace(" ", "_")
    entry = data.get("targets", {}).get(key)
    if entry is None:
        return None

    code = normalize_lang(lang)
    # Fall back to English if this target lacks the requested language.
    content = entry.get(code) or entry.get(default_language()) or {}
    available_langs = sorted(entry.keys() & {"en", "hi", "mr", "ta", "te"})

    referral = None
    if _referral_needed(confidence, risk_level):
        referral = data.get("referral", {}).get(code) or data.get("referral", {}).get(
            default_language()
        )

    return {
        "target": key,
        "language": code,
        "name": content.get("name", key),
        "management": content.get("management", []),
        "safety": content.get("safety", []),
        "followup_days": content.get("followup_days"),
        "referral": referral,
        "available_languages": available_langs,
    }
