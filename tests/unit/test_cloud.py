"""Tests for tools/cloud.py — Open-Meteo batch parsing + window averaging."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from auroragaze.schemas import NightWindow
from auroragaze.tools.cloud import cloud_cover_for_window, cloud_cover_lookup


def _night(start_iso: str, end_iso: str) -> NightWindow:
    """Tiny NightWindow factory; only the UTC anchors matter for cloud math."""
    return NightWindow(
        sunset_local="20:00",
        astro_night_start_local="21:30",
        astro_night_end_local="03:30",
        sunrise_local="06:00",
        sunset_utc=datetime.fromisoformat(start_iso).replace(tzinfo=UTC),
        sunrise_utc=datetime.fromisoformat(end_iso).replace(tzinfo=UTC),
        timezone="Australia/Hobart",
        is_daylight_now=False,
    )


@pytest.mark.asyncio
async def test_cloud_cover_returns_average_in_window(httpx_mock) -> None:  # type: ignore[no-untyped-def]
    night = _night("2026-05-04T10:00", "2026-05-04T19:00")  # ~21:00 → 06:00 local AEST
    httpx_mock.add_response(
        method="GET",
        url=__import__("re").compile(r"^https://api\.open-meteo\.com/v1/forecast.*"),
        json=[
            {
                "hourly": {
                    "time": [
                        "2026-05-04T08:00",
                        "2026-05-04T11:00",
                        "2026-05-04T15:00",
                        "2026-05-04T20:00",
                    ],
                    "cloud_cover": [10, 80, 60, 100],
                }
            }
        ],
    )
    out = await cloud_cover_for_window([(-42.88, 147.32)], night)
    # Window covers 09:00..20:00 UTC (with ±1h padding); values inside: 80, 60, 100 → avg 80.
    val = cloud_cover_lookup(out, -42.88, 147.32)
    assert 70 <= val <= 90


@pytest.mark.asyncio
async def test_cloud_cover_failure_returns_empty(httpx_mock) -> None:  # type: ignore[no-untyped-def]
    night = _night("2026-05-04T10:00", "2026-05-04T19:00")
    httpx_mock.add_response(
        method="GET",
        url=__import__("re").compile(r"^https://api\.open-meteo\.com/v1/forecast.*"),
        status_code=500,
    )
    out = await cloud_cover_for_window([(-42.88, 147.32)], night)
    assert out == {}


@pytest.mark.asyncio
async def test_cloud_cover_empty_coords_short_circuits() -> None:
    night = _night("2026-05-04T10:00", "2026-05-04T19:00")
    out = await cloud_cover_for_window([], night)
    assert out == {}


def test_cloud_cover_lookup_default() -> None:
    assert cloud_cover_lookup({}, -42.88, 147.32) == 50
    assert cloud_cover_lookup({(-42.88, 147.32): 80}, -42.88, 147.32) == 80
