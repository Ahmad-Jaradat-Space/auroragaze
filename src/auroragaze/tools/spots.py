"""Candidate aurora viewing spots inside a chaser's drive radius.

The user gives us a base lat/lon (their city) and a radius_km (5..300).
We return up to ~25 named candidate spots: viewpoints, peaks, nature
reserves, dark-sky parks tagged on OpenStreetMap. Each candidate carries
a great-circle distance and a cardinal bearing from the base. The base
itself is always candidate #0 so chasers can compare staying put with
driving out.

Design:
- Primary path: a single Overpass QL query against `overpass-api.de`.
- Fallback (Overpass down or <5 hits): a deterministic hex-grid sample
  inside the radius. Each grid point gets a bearing-based pseudo-name.
- We also fetch nearby populated places (city/town/village) with
  population — used by `light_pollution.bortle_at` to estimate sky
  glow without needing a raster dataset.

No API key required. Overpass is free and rate-limited; we time out at
12 s and fall back gracefully.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import httpx

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

EARTH_RADIUS_KM = 6371.0088

_BEARINGS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
             "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


@dataclass(frozen=True)
class Candidate:
    """A potential viewing spot, pre-ranking."""

    name: str
    lat: float
    lon: float
    distance_km: float
    bearing: str
    is_base: bool = False
    osm_kind: str = ""  # 'viewpoint' | 'peak' | 'reserve' | 'park' | 'grid' | 'base'


@dataclass(frozen=True)
class PopulatedPlace:
    """An OSM-tagged settlement (city/town/village). Used for light-pollution proxy."""

    name: str
    lat: float
    lon: float
    population: int  # 0 if unknown
    place_kind: str  # 'city', 'town', 'village', 'hamlet'


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def bearing_cardinal(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    """Initial bearing from (lat1,lon1) to (lat2,lon2) as 16-wind compass label."""
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    deg = (math.degrees(math.atan2(x, y)) + 360.0) % 360.0
    return _BEARINGS[int((deg + 11.25) // 22.5) % 16]


def _overpass_query(lat: float, lon: float, radius_m: int) -> str:
    # tourism=viewpoint, natural=peak, leisure=nature_reserve,
    # boundary=protected_area, leisure=park (large parks often dark)
    return f"""
[out:json][timeout:10];
(
  node["tourism"="viewpoint"](around:{radius_m},{lat},{lon});
  node["natural"="peak"](around:{radius_m},{lat},{lon});
  way["leisure"="nature_reserve"](around:{radius_m},{lat},{lon});
  way["boundary"="protected_area"](around:{radius_m},{lat},{lon});
  relation["leisure"="nature_reserve"](around:{radius_m},{lat},{lon});
  relation["boundary"="protected_area"](around:{radius_m},{lat},{lon});
);
out center 50;
""".strip()


def _places_query(lat: float, lon: float, radius_m: int) -> str:
    return f"""
[out:json][timeout:10];
(
  node["place"~"^(city|town|village|hamlet|suburb)$"](around:{radius_m},{lat},{lon});
);
out 60;
""".strip()


def _kind_from_tags(tags: dict[str, str]) -> str:
    if tags.get("tourism") == "viewpoint":
        return "viewpoint"
    if tags.get("natural") == "peak":
        return "peak"
    if tags.get("boundary") == "protected_area":
        return "park"
    if tags.get("leisure") in ("nature_reserve", "park"):
        return "reserve"
    return ""


def _hex_grid(base_lat: float, base_lon: float, radius_km: float) -> list[tuple[float, float]]:
    """12-point hex sampling at 1/3 and 2/3 of the radius, plus 6 outer."""
    out: list[tuple[float, float]] = []
    deg_per_km_lat = 1.0 / 110.574
    deg_per_km_lon = 1.0 / max(0.01, 111.320 * math.cos(math.radians(base_lat)))
    for ring_frac in (0.4, 0.75):
        for k in range(6):
            ang = math.radians(60.0 * k + (30.0 if ring_frac < 0.5 else 0.0))
            d = radius_km * ring_frac
            dlat = d * math.sin(ang) * deg_per_km_lat
            dlon = d * math.cos(ang) * deg_per_km_lon
            out.append((base_lat + dlat, base_lon + dlon))
    return out


def _build_base_candidate(base_lat: float, base_lon: float, base_name: str) -> Candidate:
    return Candidate(
        name=base_name or "Your location",
        lat=base_lat,
        lon=base_lon,
        distance_km=0.0,
        bearing="-",
        is_base=True,
        osm_kind="base",
    )


async def find_candidate_spots(
    lat: float,
    lon: float,
    radius_km: int,
    base_name: str = "",
    client: httpx.AsyncClient | None = None,
) -> list[Candidate]:
    """Return base + up to ~24 named candidates inside `radius_km`.

    Always non-empty: returns at least the base point. On Overpass
    failure, returns base + hex-grid samples named by bearing+distance.
    """
    radius_km = max(5, min(300, int(radius_km)))
    radius_m = int(radius_km * 1000)
    base = _build_base_candidate(lat, lon, base_name)
    candidates: list[Candidate] = [base]

    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=12.0)
    try:
        try:
            r = await client.post(
                OVERPASS_URL,
                data={"data": _overpass_query(lat, lon, radius_m)},
                headers={"User-Agent": "auroragaze/0.2 (chaser radius)"},
            )
            r.raise_for_status()
            payload = r.json()
        except Exception:
            payload = {"elements": []}
    finally:
        if own_client:
            await client.aclose()

    seen: set[tuple[float, float]] = set()
    for el in payload.get("elements", []):
        # nodes have lat/lon directly; ways/relations expose `center`
        clat = el.get("lat") or (el.get("center") or {}).get("lat")
        clon = el.get("lon") or (el.get("center") or {}).get("lon")
        if clat is None or clon is None:
            continue
        clat, clon = float(clat), float(clon)
        key = (round(clat, 4), round(clon, 4))
        if key in seen:
            continue
        seen.add(key)
        tags = el.get("tags") or {}
        name = tags.get("name") or tags.get("name:en")
        kind = _kind_from_tags(tags)
        if not name:
            # Skip nameless POIs — no UX value showing "unnamed peak".
            continue
        d = haversine_km(lat, lon, clat, clon)
        if d > radius_km + 1.0:
            continue
        bearing = bearing_cardinal(lat, lon, clat, clon)
        candidates.append(
            Candidate(
                name=name,
                lat=clat,
                lon=clon,
                distance_km=round(d, 1),
                bearing=bearing,
                osm_kind=kind or "spot",
            )
        )

    # Cap at base + 24 named POIs.
    if len(candidates) > 25:
        candidates.sort(key=lambda c: (not c.is_base, c.distance_km))
        candidates = candidates[:25]

    if len(candidates) < 6:
        # Top up with hex-grid samples so the chaser still has options.
        for plat, plon in _hex_grid(lat, lon, radius_km):
            d = haversine_km(lat, lon, plat, plon)
            bearing = bearing_cardinal(lat, lon, plat, plon)
            candidates.append(
                Candidate(
                    name=f"~{int(round(d))} km {bearing} of {base_name or 'base'}",
                    lat=plat,
                    lon=plon,
                    distance_km=round(d, 1),
                    bearing=bearing,
                    osm_kind="grid",
                )
            )

    return candidates


async def find_populated_places(
    lat: float,
    lon: float,
    radius_km: int,
    client: httpx.AsyncClient | None = None,
) -> list[PopulatedPlace]:
    """Return populated places (city/town/village/...) within radius.

    Used as a light-pollution proxy: distance to nearest place + its
    population approximates Bortle better than nothing, and requires no
    new dataset. Returns [] on Overpass failure.
    """
    radius_km = max(5, min(400, int(radius_km)))
    radius_m = int(radius_km * 1000)
    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=12.0)
    try:
        try:
            r = await client.post(
                OVERPASS_URL,
                data={"data": _places_query(lat, lon, radius_m)},
                headers={"User-Agent": "auroragaze/0.2 (light-pollution proxy)"},
            )
            r.raise_for_status()
            payload = r.json()
        except Exception:
            return []
    finally:
        if own_client:
            await client.aclose()

    out: list[PopulatedPlace] = []
    for el in payload.get("elements", []):
        plat = el.get("lat")
        plon = el.get("lon")
        if plat is None or plon is None:
            continue
        tags = el.get("tags") or {}
        name = tags.get("name") or "unnamed"
        kind = tags.get("place", "")
        try:
            pop = int(str(tags.get("population", "0")).replace(",", "").replace(" ", ""))
        except (ValueError, TypeError):
            pop = 0
        out.append(
            PopulatedPlace(
                name=name,
                lat=float(plat),
                lon=float(plon),
                population=pop,
                place_kind=kind,
            )
        )
    return out
