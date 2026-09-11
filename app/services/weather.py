"""Weather service with a swappable provider interface (offline-ready).

The app never talks to a weather API directly — it always goes through a
``WeatherProvider``. The default provider is Open-Meteo (free, no API key).
Because providers implement one interface and responses are cached on disk,
a future offline source (manual entry, on-farm sensors, a bundled climatology
table) can replace it without touching the risk engine or routers.
"""
from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path

from ..config import BASE_DIR, settings

logger = logging.getLogger(__name__)

# What the rest of the app consumes — deliberately plain dicts so any provider
# (including a future offline one) can produce them without extra deps.
DayForecast = dict  # {"date", "rain_mm", "humidity_mean", "temp_max", "wind_max"}
WeatherBundle = dict  # {"location", "latitude", "longitude", "daily": [DayForecast], "source"}


class WeatherProvider(ABC):
    """Interface every weather source implements (online or offline)."""

    name: str = "abstract"

    @abstractmethod
    def geocode(self, place: str) -> tuple[float, float] | None:
        """Resolve a place name to (lat, lon), or None if unknown."""

    @abstractmethod
    def forecast_daily(self, lat: float, lon: float, days: int = 7) -> list[DayForecast]:
        """Return up to ``days`` daily forecasts, oldest first."""


class OpenMeteoProvider(WeatherProvider):
    """Free Open-Meteo forecast + geocoding (no API key required)."""

    name = "open-meteo"

    GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
    FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

    def geocode(self, place: str) -> tuple[float, float] | None:
        import requests  # lazy: keeps boot/tests light when offline

        try:
            resp = requests.get(
                self.GEOCODE_URL,
                params={"name": place, "count": 1, "language": "en", "format": "json"},
                timeout=10,
            )
            resp.raise_for_status()
            results = resp.json().get("results") or []
        except Exception as exc:  # noqa: BLE001 — network errors must not crash the API
            logger.warning("Geocoding failed for %r: %s", place, exc)
            return None
        if not results:
            return None
        top = results[0]
        return float(top["latitude"]), float(top["longitude"])

    def forecast_daily(self, lat: float, lon: float, days: int = 7) -> list[DayForecast]:
        import requests

        try:
            resp = requests.get(
                self.FORECAST_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "daily": "temperature_2m_max,relative_humidity_2m_mean,"
                    "precipitation_sum,wind_speed_10m_max",
                    "forecast_days": min(max(days, 1), 16),
                    "timezone": "auto",
                },
                timeout=10,
            )
            resp.raise_for_status()
            daily = resp.json().get("daily") or {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Forecast fetch failed for (%s, %s): %s", lat, lon, exc)
            return []

        dates = daily.get("time") or []
        rain = daily.get("precipitation_sum") or []
        humidity = daily.get("relative_humidity_2m_mean") or []
        tmax = daily.get("temperature_2m_max") or []
        wind = daily.get("wind_speed_10m_max") or []
        out: list[DayForecast] = []
        for i, date in enumerate(dates):
            out.append(
                {
                    "date": date,
                    "rain_mm": _num(rain, i),
                    "humidity_mean": _num(humidity, i),
                    "temp_max": _num(tmax, i),
                    "wind_max": _num(wind, i),
                }
            )
        return out


def _num(values: list, i: int) -> float | None:
    if i >= len(values):
        return None
    try:
        return float(values[i])
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Disk cache — the offline lifeline. When the network is down the risk engine
# keeps working from the last successful fetch (within the configured TTL).
# ---------------------------------------------------------------------------
def _cache_path() -> Path:
    path = settings.weather_cache_path
    return path if path.is_absolute() else BASE_DIR / path


def _load_cache() -> dict:
    path = _cache_path()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — missing/corrupt cache is fine
        return {}


def _save_cache(cache: dict) -> None:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


def _cache_key(lat: float, lon: float, days: int) -> str:
    return f"{round(lat, 2)},{round(lon, 2)},{days}"


def get_weather(
    location: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    days: int = 7,
) -> WeatherBundle | None:
    """Weather for a place/point, served from cache when possible.

    Resolution order: cache hit (fresh) -> live fetch (cached afterwards) ->
    stale cache entry (offline fallback) -> None.
    """
    provider_name = settings.weather_provider
    if provider_name not in ("open-meteo",):
        logger.warning("Unknown weather provider %r — using open-meteo", provider_name)
        provider_name = "open-meteo"
    provider: WeatherProvider = OpenMeteoProvider()

    if lat is None or lon is None:
        if not location:
            raise ValueError("Provide either a location name or lat/lon")
        coords = provider.geocode(location)
        if coords is None:
            return None
        lat, lon = coords

    ttl = settings.weather_cache_ttl_hours * 3600
    cache = _load_cache()
    key = _cache_key(lat, lon, days)
    entry = cache.get(key)
    if entry and (time.time() - entry.get("fetched_at", 0)) < ttl:
        return entry["data"]

    daily = provider.forecast_daily(lat, lon, days)
    if daily:
        bundle: WeatherBundle = {
            "location": location,
            "latitude": lat,
            "longitude": lon,
            "daily": daily,
            "source": provider.name,
        }
        cache[key] = {"fetched_at": time.time(), "data": bundle}
        try:
            _save_cache(cache)
        except OSError as exc:  # read-only FS etc. — never fatal
            logger.warning("Could not write weather cache: %s", exc)
        return bundle

    # Live fetch failed — fall back to a stale cache entry if one exists.
    if entry:
        logger.info("Weather fetch failed; serving stale cache for %s", key)
        stale = dict(entry["data"])
        stale["stale"] = True
        return stale
    return None
