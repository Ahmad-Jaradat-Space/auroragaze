"""Tests for tools/spots.py — Overpass query, parsing, distance/bearing, fallback."""

from __future__ import annotations

import pytest

from auroragaze.tools.spots import (
    bearing_cardinal,
    find_candidate_spots,
    find_populated_places,
    haversine_km,
)

# Hobart base for parametrised tests.
HOBART_LAT = -42.88
HOBART_LON = 147.32


def test_haversine_zero_distance() -> None:
    assert haversine_km(0, 0, 0, 0) == pytest.approx(0.0)


def test_haversine_known_pair() -> None:
    # Hobart → Sydney, ~1037 km great-circle.
    d = haversine_km(HOBART_LAT, HOBART_LON, -33.87, 151.21)
    assert 1000.0 < d < 1100.0


def test_bearing_cardinal_north() -> None:
    assert bearing_cardinal(0, 0, 1, 0) == "N"


def test_bearing_cardinal_east() -> None:
    assert bearing_cardinal(0, 0, 0, 1) == "E"


def test_bearing_cardinal_south() -> None:
    assert bearing_cardinal(0, 0, -1, 0) == "S"


def test_bearing_cardinal_southwest() -> None:
    assert bearing_cardinal(0, 0, -1, -1) in {"SW", "SSW", "WSW"}


@pytest.mark.asyncio
async def test_find_candidate_spots_parses_overpass(httpx_mock) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "elements": [
            {
                "type": "node",
                "id": 1,
                "lat": -42.95,
                "lon": 147.24,
                "tags": {"tourism": "viewpoint", "name": "Mount Nelson Lookout"},
            },
            {
                "type": "node",
                "id": 2,
                "lat": -43.10,
                "lon": 147.30,
                "tags": {"natural": "peak", "name": "Mt Wellington"},
            },
            {
                "type": "way",
                "id": 3,
                "center": {"lat": -43.20, "lon": 147.10},
                "tags": {"leisure": "nature_reserve", "name": "Peter Murrell Reserve"},
            },
            {
                "type": "node",
                "id": 4,
                "lat": -42.80,
                "lon": 147.30,
                "tags": {"tourism": "viewpoint"},  # nameless — should be skipped
            },
        ]
    }
    httpx_mock.add_response(
        method="POST",
        url="https://overpass-api.de/api/interpreter",
        json=payload,
    )
    out = await find_candidate_spots(HOBART_LAT, HOBART_LON, 80, base_name="Hobart")
    assert out, "must return at least the base"
    assert out[0].is_base is True
    names = {c.name for c in out if not c.is_base}
    assert "Mount Nelson Lookout" in names
    assert "Mt Wellington" in names
    assert "Peter Murrell Reserve" in names
    # Nameless node should be skipped, so we have exactly 3 named POIs (or +grid fallback).
    osm_kinds = {c.osm_kind for c in out if not c.is_base}
    assert "viewpoint" in osm_kinds or "peak" in osm_kinds or "reserve" in osm_kinds
    # Distances are non-negative; base is at zero.
    assert all(c.distance_km >= 0 for c in out)
    assert out[0].distance_km == 0.0


@pytest.mark.asyncio
async def test_find_candidate_spots_falls_back_on_failure(httpx_mock) -> None:  # type: ignore[no-untyped-def]
    httpx_mock.add_response(
        method="POST",
        url="https://overpass-api.de/api/interpreter",
        status_code=503,
    )
    out = await find_candidate_spots(HOBART_LAT, HOBART_LON, 60, base_name="Hobart")
    # Always at least the base + hex grid (12 points).
    assert out[0].is_base is True
    assert len(out) >= 12  # base + 11 grid filling up
    # All grid candidates must have a known bearing label.
    for c in out[1:]:
        assert c.bearing in {
            "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
        }


@pytest.mark.asyncio
async def test_find_candidate_spots_clamps_radius(httpx_mock) -> None:  # type: ignore[no-untyped-def]
    httpx_mock.add_response(
        method="POST",
        url="https://overpass-api.de/api/interpreter",
        json={"elements": []},
    )
    # Pass an absurd radius — must clamp without crashing.
    out = await find_candidate_spots(HOBART_LAT, HOBART_LON, 9999, base_name="Hobart")
    assert out[0].is_base


@pytest.mark.asyncio
async def test_find_populated_places_parses(httpx_mock) -> None:  # type: ignore[no-untyped-def]
    payload = {
        "elements": [
            {
                "type": "node",
                "id": 1,
                "lat": -42.88,
                "lon": 147.32,
                "tags": {"place": "city", "name": "Hobart", "population": "240,000"},
            },
            {
                "type": "node",
                "id": 2,
                "lat": -42.79,
                "lon": 147.06,
                "tags": {"place": "town", "name": "New Norfolk", "population": "5500"},
            },
            {
                "type": "node",
                "id": 3,
                "lat": -43.00,
                "lon": 147.30,
                "tags": {"place": "village", "name": "Kingston"},
            },
        ]
    }
    httpx_mock.add_response(
        method="POST",
        url="https://overpass-api.de/api/interpreter",
        json=payload,
    )
    out = await find_populated_places(HOBART_LAT, HOBART_LON, 80)
    pops = {p.name: p for p in out}
    assert "Hobart" in pops and pops["Hobart"].population == 240_000
    assert "New Norfolk" in pops and pops["New Norfolk"].population == 5500
    # Kingston has no population tag → 0
    assert pops["Kingston"].population == 0
