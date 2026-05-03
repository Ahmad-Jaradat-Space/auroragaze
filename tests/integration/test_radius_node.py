"""Integration test for the new nearby_spots_node.

Exercises the node in isolation with mocked Overpass + Open-Meteo so we
verify the pipeline glues together without depending on the LLM. The full
graph is covered separately by smoke runs against the live API.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest

from auroragaze.graph import nearby_spots_node
from auroragaze.schemas import KpBin, KpForecast, NightWindow


def _state() -> dict:
    night = NightWindow(
        sunset_local="20:00",
        civil_dusk_local="20:30",
        astro_night_start_local="21:30",
        astro_night_end_local="03:30",
        civil_dawn_local="04:30",
        sunrise_local="05:00",
        sunset_utc=datetime(2026, 5, 4, 10, 0, tzinfo=UTC),
        sunrise_utc=datetime(2026, 5, 4, 19, 0, tzinfo=UTC),
        timezone="Australia/Hobart",
        is_daylight_now=False,
    )
    bins = [
        KpBin(start=datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
              end=datetime(2026, 5, 4, 12, 0, tzinfo=UTC), kp=5.5),
        KpBin(start=datetime(2026, 5, 4, 12, 0, tzinfo=UTC),
              end=datetime(2026, 5, 4, 15, 0, tzinfo=UTC), kp=6.0),
        KpBin(start=datetime(2026, 5, 4, 15, 0, tzinfo=UTC),
              end=datetime(2026, 5, 4, 18, 0, tzinfo=UTC), kp=5.0),
    ]
    return {
        "persona": "aurora",
        "lat": -42.88,
        "lon": 147.32,
        "location_label": "Hobart, TAS",
        "radius_km": 60,
        "night_window": night,
        "kp_forecast": KpForecast(bins=bins, issued=datetime(2026, 5, 4, 8, 0, tzinfo=UTC)),
    }


@pytest.mark.asyncio
async def test_nearby_spots_node_produces_ranked_list(httpx_mock) -> None:  # type: ignore[no-untyped-def]
    # Two Overpass calls — viewpoints/peaks first, then populated places.
    httpx_mock.add_response(
        method="POST",
        url="https://overpass-api.de/api/interpreter",
        json={
            "elements": [
                {"type": "node", "id": 1, "lat": -42.95, "lon": 147.24,
                 "tags": {"tourism": "viewpoint", "name": "Mount Nelson"}},
                {"type": "node", "id": 2, "lat": -43.20, "lon": 147.30,
                 "tags": {"natural": "peak", "name": "Mt Wellington"}},
                {"type": "node", "id": 3, "lat": -43.40, "lon": 147.30,
                 "tags": {"tourism": "viewpoint", "name": "Bruny Lookout"}},
            ]
        },
    )
    httpx_mock.add_response(
        method="POST",
        url="https://overpass-api.de/api/interpreter",
        json={
            "elements": [
                {"type": "node", "id": 100, "lat": -42.88, "lon": 147.32,
                 "tags": {"place": "city", "name": "Hobart", "population": "240000"}},
            ]
        },
    )
    httpx_mock.add_response(
        method="GET",
        url=re.compile(r"^https://api\.open-meteo\.com/v1/forecast.*"),
        json=[
            # base — overcast
            {"hourly": {"time": ["2026-05-04T11:00", "2026-05-04T15:00"],
                        "cloud_cover": [90, 90]}},
            # Mount Nelson — partly cloudy
            {"hourly": {"time": ["2026-05-04T11:00", "2026-05-04T15:00"],
                        "cloud_cover": [50, 50]}},
            # Mt Wellington — clear
            {"hourly": {"time": ["2026-05-04T11:00", "2026-05-04T15:00"],
                        "cloud_cover": [10, 10]}},
            # Bruny Lookout — clear
            {"hourly": {"time": ["2026-05-04T11:00", "2026-05-04T15:00"],
                        "cloud_cover": [15, 15]}},
        ],
    )

    out = await nearby_spots_node(_state())
    assert "ranked_spots" in out
    ranked = out["ranked_spots"]
    assert ranked, "should produce at least one ranked spot"
    assert ranked[0].rank == 1
    # Best bet should NOT be the cloudy base — clear spots win.
    assert ranked[0].name in {"Mt Wellington", "Bruny Lookout", "Mount Nelson"}
    # Base must still be present.
    bases = [r for r in ranked if r.is_base]
    assert len(bases) == 1
    # Radius is echoed back into the trace.
    assert out["radius_km"] == 60
