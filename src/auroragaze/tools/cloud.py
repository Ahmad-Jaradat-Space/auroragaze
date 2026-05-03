"""Cloud-cover forecast for tonight's viewing window, per candidate spot.

Backed by Open-Meteo's free `forecast` endpoint — no API key, generous
quotas, accepts comma-separated latitudes/longitudes for batch lookup.

We request hourly `cloud_cover` (0..100 %) for the day surrounding the
night window, then average the values that fall inside the window for
each spot. Returns a `dict[(lat, lon), int]` of mean cloud cover
percentages. On any failure we return an empty dict — the ranker
treats absent data as 50 % (neutral) so the pipeline never crashes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from auroragaze.schemas import NightWindow

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def _date_range_for_window(night: NightWindow) -> tuple[str, str]:
    """Open-Meteo wants ISO dates (UTC). Cover sunset day → sunrise day."""
    d_start = night.sunset_utc.date()
    d_end = night.sunrise_utc.date()
    if d_end < d_start:
        d_end = d_start
    return d_start.isoformat(), d_end.isoformat()


def _round_coord(v: float) -> float:
    # Open-Meteo dedupes coords; rounding to 3dp (~110 m) keeps batch small.
    return round(v, 3)


async def cloud_cover_for_window(
    coords: list[tuple[float, float]],
    night: NightWindow,
    client: httpx.AsyncClient | None = None,
) -> dict[tuple[float, float], int]:
    """Return mean cloud cover (%) over [sunset_utc, sunrise_utc] per coord.

    Empty input or HTTP failure returns an empty dict.
    """
    if not coords:
        return {}

    rounded = [(_round_coord(la), _round_coord(lo)) for la, lo in coords]
    # Open-Meteo silently dedupes by sequence position, so we keep the
    # full list and map back via index.
    lats = ",".join(f"{la}" for la, _ in rounded)
    lons = ",".join(f"{lo}" for _, lo in rounded)

    start_date, end_date = _date_range_for_window(night)
    params = {
        "latitude": lats,
        "longitude": lons,
        "hourly": "cloud_cover",
        "start_date": start_date,
        "end_date": end_date,
        "timezone": "UTC",
    }

    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=10.0)
    try:
        try:
            r = await client.get(OPEN_METEO_URL, params=params)
            r.raise_for_status()
            payload = r.json()
        except Exception:
            return {}
    finally:
        if own_client:
            await client.aclose()

    # Single-coord requests return a dict; multi-coord requests return a list.
    spots = payload if isinstance(payload, list) else [payload]
    out: dict[tuple[float, float], int] = {}
    sunset = night.sunset_utc.astimezone(UTC).replace(tzinfo=None)
    sunrise = night.sunrise_utc.astimezone(UTC).replace(tzinfo=None)

    for idx, spot in enumerate(spots):
        if idx >= len(rounded):
            break
        hourly = spot.get("hourly") or {}
        times: list[str] = hourly.get("time") or []
        values: list[float | None] = hourly.get("cloud_cover") or []
        in_window: list[float] = []
        for t_str, v in zip(times, values, strict=False):
            if v is None:
                continue
            try:
                t = datetime.fromisoformat(t_str)
            except ValueError:
                continue
            # Open-Meteo with timezone=UTC returns naive UTC ISO strings.
            if sunset - timedelta(hours=1) <= t <= sunrise + timedelta(hours=1):
                in_window.append(float(v))
        if in_window:
            out[rounded[idx]] = int(round(sum(in_window) / len(in_window)))

    return out


def cloud_cover_lookup(
    lookup: dict[tuple[float, float], int],
    lat: float,
    lon: float,
    default: int = 50,
) -> int:
    """Fetch the cloud value for a coord from the lookup, with a sane default."""
    return lookup.get((_round_coord(lat), _round_coord(lon)), default)
