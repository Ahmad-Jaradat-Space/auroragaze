"""Tests for tools/ranker.py — composite scoring + ranking invariants."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from auroragaze.schemas import KpBin, NightWindow
from auroragaze.tools.physics import assess_visibility
from auroragaze.tools.ranker import _distance_penalty, _geomag_score, rank_spots
from auroragaze.tools.spots import Candidate


def _night() -> NightWindow:
    return NightWindow(
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


def _bins(kp: float = 6.0) -> list[KpBin]:
    start = datetime(2026, 5, 4, 11, 0, tzinfo=UTC)
    return [
        KpBin(start=start + timedelta(hours=3 * i), end=start + timedelta(hours=3 * (i + 1)), kp=kp)
        for i in range(4)
    ]


def _base() -> Candidate:
    return Candidate(
        name="Hobart", lat=-42.88, lon=147.32, distance_km=0.0, bearing="-",
        is_base=True, osm_kind="base",
    )


def _spot(name: str, lat: float, lon: float, dist: float, bearing: str = "S") -> Candidate:
    return Candidate(
        name=name, lat=lat, lon=lon, distance_km=dist, bearing=bearing,
        is_base=False, osm_kind="viewpoint",
    )


def test_geomag_score_at_boundary_is_half() -> None:
    # Margin = 0 → score 0.5
    v = assess_visibility(lat=-46.0, lon=147.0, kp=5.0)
    assert abs(_geomag_score(v, abs(-v.boundary_lat_deg)) - 0.5) < 0.01


def test_distance_penalty_monotonic() -> None:
    assert _distance_penalty(0.0) == 0.0
    assert 0.0 < _distance_penalty(40.0) < _distance_penalty(160.0) < 1.0


def test_clear_skies_outrank_cloudy_base() -> None:
    """A 30 km drive to clear skies should beat staying at a cloudy base."""
    base = _base()
    away = _spot("Tinderbox", -43.05, 147.32, 30.0, "S")
    cloud_lookup = {(round(base.lat, 3), round(base.lon, 3)): 90,
                    (round(away.lat, 3), round(away.lon, 3)): 10}
    bortle_lookup = {(round(base.lat, 3), round(base.lon, 3)): 7,
                     (round(away.lat, 3), round(away.lon, 3)): 3}
    ranked = rank_spots(
        base_lat=base.lat,
        candidates=[base, away],
        night=_night(),
        bins=_bins(6.0),
        cloud_lookup=cloud_lookup,
        bortle_lookup=bortle_lookup,
    )
    # Top spot must be the clear-sky away spot, not the cloudy base.
    assert ranked[0].name == "Tinderbox"
    assert ranked[0].rank == 1


def test_base_always_present_and_marked() -> None:
    base = _base()
    away = _spot("Far Away", -45.0, 147.0, 250.0, "S")
    cloud_lookup: dict[tuple[float, float], int] = {}
    bortle_lookup: dict[tuple[float, float], int] = {}
    ranked = rank_spots(
        base_lat=base.lat,
        candidates=[base, away],
        night=_night(),
        bins=_bins(5.0),
        cloud_lookup=cloud_lookup,
        bortle_lookup=bortle_lookup,
    )
    bases = [r for r in ranked if r.is_base]
    assert len(bases) == 1
    assert bases[0].name == "Hobart"


def test_ranks_are_sequential_starting_at_one() -> None:
    candidates = [_base()] + [
        _spot(f"S{i}", -42.88 - 0.05 * i, 147.32, 5.0 * i) for i in range(1, 5)
    ]
    ranked = rank_spots(
        base_lat=-42.88,
        candidates=candidates,
        night=_night(),
        bins=_bins(7.0),
        cloud_lookup={},
        bortle_lookup={},
    )
    assert [r.rank for r in ranked] == list(range(1, len(ranked) + 1))


def test_distance_penalty_breaks_near_ties() -> None:
    """Two spots with identical conditions but different distances rank by distance."""
    base = _base()
    near = _spot("Near", -43.00, 147.32, 15.0, "S")
    far = _spot("Far", -43.50, 147.32, 70.0, "S")
    cloud_lookup = {(round(c.lat, 3), round(c.lon, 3)): 50 for c in (base, near, far)}
    bortle_lookup = {(round(c.lat, 3), round(c.lon, 3)): 4 for c in (base, near, far)}
    ranked = rank_spots(
        base_lat=base.lat,
        candidates=[base, near, far],
        night=_night(),
        bins=_bins(6.0),
        cloud_lookup=cloud_lookup,
        bortle_lookup=bortle_lookup,
    )
    by_name = {r.name: r for r in ranked}
    assert by_name["Near"].rank < by_name["Far"].rank


def test_empty_candidates_returns_empty() -> None:
    assert rank_spots(
        base_lat=-42.88,
        candidates=[],
        night=_night(),
        bins=_bins(),
        cloud_lookup={},
        bortle_lookup={},
    ) == []
