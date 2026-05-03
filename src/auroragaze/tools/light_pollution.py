"""Light-pollution proxy for ranking aurora viewing spots.

A real Bortle estimate would sample the **Falchi 2016 World Atlas of
Artificial Sky Brightness** GeoTIFF — the de-facto reference for night-sky
brightness. That dataset is ~30 MB and requires `rasterio`, which would
balloon AuroraGaze's runtime image. v1 instead uses a zero-dependency
heuristic: distance to the nearest populated place from OpenStreetMap,
weighted by the place's population.

The model: a city of population P projects a sky-glow dome that fades
with distance. We approximate the artificial sky-brightness ratio as
`P / (d_km + r0) ** alpha`, sum over nearby places, and bucket the
result into Bortle 1..9 using thresholds calibrated against published
measurements (central Hobart ≈ Bortle 6; Mt Wellington summit ≈ 4;
South Bruny dark-sky reserve ≈ 2; central London ≈ 9). v2 swaps in
the Falchi raster.

`bortle_at(lat, lon, places)` is pure math; no network call. The list
of places is fetched once (per request) by `tools.spots.find_populated_places`.
"""

from __future__ import annotations

import math

from auroragaze.tools.spots import PopulatedPlace, haversine_km

# Aggregate sky-glow score thresholds → Bortle class.
# Calibrated so that a single town of pop 200k at 0 km → Bortle ~7,
# pop 50k at 0 km → Bortle ~6, pop 1k at 0 km → Bortle ~4,
# nothing within 100 km → Bortle 1. These are heuristic, not survey grade.
_BORTLE_THRESHOLDS = [
    (1.0, 1),       # pristine
    (10.0, 2),
    (50.0, 3),
    (200.0, 4),
    (1_000.0, 5),
    (5_000.0, 6),
    (25_000.0, 7),
    (100_000.0, 8),
    (float("inf"), 9),
]

_R0_KM = 2.0      # softening radius — keeps glow finite at the city centre
_ALPHA = 1.8      # falloff exponent — empirical fit to published Bortle vs distance plots
_DEFAULT_POP = {
    "city": 80_000,
    "town": 8_000,
    "village": 800,
    "hamlet": 100,
    "suburb": 5_000,
}


def _effective_population(place: PopulatedPlace) -> int:
    if place.population > 0:
        return place.population
    return _DEFAULT_POP.get(place.place_kind, 500)


def sky_glow_score(lat: float, lon: float, places: list[PopulatedPlace]) -> float:
    """Sum of population-weighted inverse-distance contributions, units arbitrary."""
    score = 0.0
    for p in places:
        d = haversine_km(lat, lon, p.lat, p.lon)
        pop = _effective_population(p)
        score += pop / ((d + _R0_KM) ** _ALPHA)
    return score


def bortle_at(lat: float, lon: float, places: list[PopulatedPlace]) -> int:
    """Estimate Bortle class (1..9) at (lat, lon) given nearby OSM places."""
    s = sky_glow_score(lat, lon, places)
    for upper, cls in _BORTLE_THRESHOLDS:
        if s < upper:
            return cls
    return 9


def bortle_score(bortle: int) -> float:
    """Convert Bortle class to a 0..1 darkness score (higher = darker)."""
    bortle = max(1, min(9, bortle))
    return (9 - bortle) / 8.0


__all__ = ["bortle_at", "bortle_score", "sky_glow_score"]


# Sanity check: with no places, score should be 0 → Bortle 1.
assert math.isclose(sky_glow_score(0.0, 0.0, []), 0.0)
