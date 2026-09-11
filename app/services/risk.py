"""Risk engine: weather rules + local history + crop stage -> per-pest risk.

Rule data lives in ``data/pest_rules.json`` and is loaded at request time, so
extension staff can tune thresholds without touching code. Everything is local
data — the engine works offline whenever the weather bundle is available from
the cache (see services.weather).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..config import BASE_DIR

RULES_PATH = BASE_DIR / "data" / "pest_rules.json"

LEVELS = ("low", "medium", "high", "severe")
_LEVEL_BREAKS = {0.25: "medium", 0.5: "high", 0.75: "severe"}


def _level_for(score: float) -> str:
    level = "low"
    for break_at, name in _LEVEL_BREAKS.items():
        if score >= break_at:
            level = name
    return level


@lru_cache(maxsize=1)
def load_rules() -> dict:
    """Read the rules file (cached; reload tests can call cache_clear)."""
    try:
        return json.loads(RULES_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"rules": [], "history": {}, "susceptible_stages": [], "stage_bonus": 0.0}


# --------------------------------------------------------------- metrics ----
def window_summary(weather: dict, window_days: int) -> dict:
    """Aggregate the risk-window metrics from a WeatherBundle's daily list."""
    days = (weather or {}).get("daily") or []
    use = days[: max(window_days, 1)]
    if not use:
        return {}
    rain = sum((d.get("rain_mm") or 0.0) for d in use)
    humidity = [d.get("humidity_mean") for d in use if d.get("humidity_mean") is not None]
    temps = [d.get("temp_max") for d in use if d.get("temp_max") is not None]
    return {
        "rain_mm": round(rain, 1),
        "humidity_mean": round(sum(humidity) / len(humidity), 1) if humidity else None,
        "temp_max": round(max(t for t in temps if t is not None), 1) if temps else None,
        "days": len(use),
    }


def _op(metric_value: float | None, op: str, rule_value) -> bool:
    if metric_value is None:
        return False
    try:
        if op == ">=":
            return metric_value >= float(rule_value)
        if op == "<=":
            return metric_value <= float(rule_value)
        if op == "between":
            lo, hi = rule_value
            return float(lo) <= metric_value <= float(hi)
    except (TypeError, ValueError):
        return False
    return False


def _match_conditions(summary: dict, rule: dict) -> tuple[bool, list[str]]:
    """Check a rule's conditions against the window summary.

    Returns (matched, human-readable drivers).
    """
    matched_drivers: list[str] = []
    ops = [c["op"] for c in rule.get("conditions", [])]
    require_all = rule.get("mode", "all") == "all"
    results = []
    for cond in rule.get("conditions", []):
        metric = cond["metric"]
        ok = _op(summary.get(metric), cond["op"], cond["value"])
        results.append(ok)
        if ok:
            value = cond["value"]
            if cond["op"] == "between":
                driver = f"{metric.replace('_', ' ')} {summary.get(metric)} (in {value[0]}–{value[1]})"
            else:
                driver = f"{metric.replace('_', ' ')} {summary.get(metric)} ({cond['op']} {value})"
            matched_drivers.append(driver)
    matched = all(results) if require_all else any(results)
    return matched, matched_drivers


# ------------------------------------------------------------ evaluation ----
def evaluate(
    weather: dict,
    crop: str | None = None,
    crop_stage: str | None = None,
    nearby_affected: int = 0,
) -> dict:
    """Score every rule target for the given context.

    Args:
        weather: WeatherBundle from services.weather.get_weather (may be None).
        crop: crop name (e.g. "rice") — rules are filtered by crop affinity.
        crop_stage: growth stage ("seedling", "vegetative", "flowering", ...).
        nearby_affected: number of affected scans/reports near the location.

    Returns:
        dict with keys ``per_pest`` (list), ``weather_summary``,
        ``history_driver``.
    """
    rules = load_rules()
    history_cfg = rules.get("history", {})
    h_days = history_cfg.get("days", 14)
    h_radius = history_cfg.get("radius_km", 25)

    scores: dict[str, dict] = {}
    crop_l = (crop or "").strip().lower()
    weather_summary: dict = {}

    if weather:
        for rule in rules.get("rules", []):
            crops = rule.get("crops", ["*"])
            if crop_l and "*" not in crops and crop_l not in crops:
                continue
            if not weather_summary:
                weather_summary = window_summary(weather, rule.get("window_days", 3))
            matched, drivers = _match_conditions(
                window_summary(weather, rule.get("window_days", 3)), rule
            )
            if not matched:
                continue
            entry = scores.setdefault(
                rule["target"], {"target": rule["target"], "score": 0.0, "drivers": []}
            )
            entry["score"] += float(rule.get("weight", 0.0))
            entry["drivers"].extend(drivers)

    # History driver: applies to every matched target (local outbreak signal).
    history_driver = None
    if nearby_affected > 0:
        history_driver = (history_cfg.get("driver") or "").format(
            radius_km=h_radius, n=nearby_affected, days=h_days
        )

    # Crop stage susceptibility bonus.
    stage_l = (crop_stage or "").strip().lower()
    stage_bonus = float(rules.get("stage_bonus", 0.0))
    stage_applies = bool(stage_l) and stage_l in rules.get("susceptible_stages", [])

    per_pest: list[dict] = []
    for target, entry in scores.items():
        score = entry["score"]
        drivers = list(dict.fromkeys(entry["drivers"]))  # de-dup, keep order
        if history_driver:
            drivers.append(history_driver)
        if stage_applies:
            score += stage_bonus
            drivers.append(f"crop at susceptible stage ({stage_l})")
        per_pest.append(
            {
                "target": target,
                "score": round(min(score, 1.0), 2),
                "level": _level_for(min(score, 1.0)),
                "drivers": drivers,
            }
        )

    per_pest.sort(key=lambda p: p["score"], reverse=True)
    overall = per_pest[0]["level"] if per_pest else "low"
    return {
        "overall_level": overall,
        "per_pest": per_pest,
        "weather_summary": weather_summary,
        "history_driver": history_driver,
        "weather_stale": bool(weather.get("stale")) if weather else False,
    }
