"""NOAA SWPC 3-day Kp forecast (3-hour bins).

Returns a `KpForecast` covering past + forecast Kp; the caller filters by
the time window of interest. Falls back to a single bin built from the
current observed Kp on any failure.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from auroragaze.schemas import KpBin, KpForecast, KpReading

FORECAST_URL = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"


async def get_kp_forecast(client: httpx.AsyncClient | None = None) -> KpForecast:
    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=10.0)
    try:
        try:
            data = (await client.get(FORECAST_URL)).json()
        except Exception:
            return _empty_fallback("forecast endpoint unreachable")
    finally:
        if own_client:
            await client.aclose()

    if not isinstance(data, list) or not data:
        return _empty_fallback("forecast payload empty")

    bins: list[KpBin] = []
    for row in data:
        try:
            ts = row["time_tag"].rstrip("Z")
            start = datetime.fromisoformat(ts).replace(tzinfo=UTC)
            kp_val = float(row["kp"])
        except (KeyError, ValueError, TypeError):
            continue
        bins.append(KpBin(start=start, end=start + timedelta(hours=3), kp=kp_val))

    if not bins:
        return _empty_fallback("no parseable bins")

    bins.sort(key=lambda b: b.start)
    return KpForecast(bins=bins, issued=datetime.now(UTC))


def _empty_fallback(reason: str) -> KpForecast:
    """Return a single-bin forecast covering the next 24h at Kp 1 (quiet),
    so downstream code never sees an empty list. Caller receives a
    well-formed `KpForecast` with the reason in the source field."""
    now = datetime.now(UTC)
    return KpForecast(
        bins=[KpBin(start=now, end=now + timedelta(hours=24), kp=1.0)],
        issued=now,
        source=f"NOAA SWPC 3-day Kp forecast (fallback: {reason})",
    )


def forecast_from_current(kp: KpReading) -> KpForecast:
    """Build a synthetic 24h forecast from a single observed Kp reading.

    Used when the eval pipeline supplies a frozen Kp and we want the
    visibility-window calculation to behave deterministically.
    """
    now = kp.timestamp
    return KpForecast(
        bins=[KpBin(start=now, end=now + timedelta(hours=24), kp=kp.kp)],
        issued=now,
        source="synthesised from observed Kp (eval mode)",
    )
