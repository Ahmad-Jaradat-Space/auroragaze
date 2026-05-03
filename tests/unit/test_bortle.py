"""Tests for tools/light_pollution.py — OSM-based Bortle proxy."""

from __future__ import annotations

from auroragaze.tools.light_pollution import bortle_at, bortle_score, sky_glow_score
from auroragaze.tools.spots import PopulatedPlace


def _city(name: str, lat: float, lon: float, pop: int, kind: str = "city") -> PopulatedPlace:
    return PopulatedPlace(name=name, lat=lat, lon=lon, population=pop, place_kind=kind)


def test_bortle_pristine_with_no_places() -> None:
    assert bortle_at(-43.4, 147.0, []) == 1


def test_bortle_central_hobart_high() -> None:
    # Sitting in the city centre of a 240k-pop city must read as bright sky.
    places = [_city("Hobart", -42.88, 147.32, 240_000)]
    assert bortle_at(-42.88, 147.32, places) >= 7


def test_bortle_drops_off_with_distance() -> None:
    places = [_city("Hobart", -42.88, 147.32, 240_000)]
    near = bortle_at(-42.88, 147.32, places)
    medium = bortle_at(-43.20, 147.30, places)  # ~35 km south
    far = bortle_at(-43.60, 147.30, places)     # ~80 km south
    assert near >= medium >= far
    assert far <= 4


def test_bortle_score_inverts_class() -> None:
    assert bortle_score(1) == 1.0
    assert bortle_score(9) == 0.0
    assert 0.4 < bortle_score(5) < 0.6


def test_sky_glow_additive() -> None:
    a = _city("A", 0.0, 0.0, 100_000)
    b = _city("B", 0.05, 0.05, 100_000)
    s_one = sky_glow_score(0.0, 0.0, [a])
    s_two = sky_glow_score(0.0, 0.0, [a, b])
    assert s_two > s_one


def test_bortle_clamps_to_valid_range() -> None:
    huge = [_city("Megacity", 0.0, 0.0, 50_000_000)]
    assert 1 <= bortle_at(0.0, 0.0, huge) <= 9
