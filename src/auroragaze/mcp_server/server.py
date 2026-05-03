"""MCP server for AuroraGaze.

Exposes seven tools to any MCP client (Claude Desktop, Cursor, internal ops):

- get_solar_wind         — live DSCOVR Bz / speed / density
- get_kp_now             — current planetary Kp
- get_dst_now            — current Dst
- assess_visibility      — auroral visibility for a location at given Kp
- compute_drag_delta     — atmospheric drag fraction for an LEO altitude + Kp
- retrieve_context       — semantic search over the curated event corpus
- nearby_viewing_spots   — ranked aurora viewing spots within drive radius

Run with: `python -m auroragaze.mcp_server.server`
Test with: `mcp dev src/auroragaze/mcp_server/server.py`
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from auroragaze.retrieval.retriever import retrieve
from auroragaze.tools.cloud import cloud_cover_for_window
from auroragaze.tools.drag import compute_drag_delta
from auroragaze.tools.dst import get_dst_now as _dst
from auroragaze.tools.kp import get_kp_now as _kp
from auroragaze.tools.kp_forecast import forecast_from_current, get_kp_forecast
from auroragaze.tools.light_pollution import bortle_at
from auroragaze.tools.night import local_night
from auroragaze.tools.physics import assess_visibility as _vis
from auroragaze.tools.ranker import rank_spots
from auroragaze.tools.solar_wind import get_solar_wind as _sw
from auroragaze.tools.spots import find_candidate_spots, find_populated_places

mcp = FastMCP("auroragaze")


@mcp.tool()
async def get_solar_wind() -> dict[str, Any]:
    """Live solar wind at L1 from NOAA DSCOVR (Bz, speed, density, timestamp)."""
    sw = await _sw()
    return sw.model_dump(mode="json")


@mcp.tool()
async def get_kp_now() -> dict[str, Any]:
    """Most recent NOAA planetary K-index value (3-hour cadence)."""
    kp = await _kp()
    return kp.model_dump(mode="json")


@mcp.tool()
async def get_dst_now() -> dict[str, Any]:
    """Most recent Dst value (Kyoto WDC via NOAA SWPC mirror)."""
    dst = await _dst()
    return dst.model_dump(mode="json")


@mcp.tool()
def assess_visibility(lat: float, lon: float, kp: float) -> dict[str, Any]:
    """Aurora visibility from a viewing location at a given Kp.

    Returns visibility level (likely / possible / unlikely), the equatorward
    threshold latitude, and a one-line reasoning.
    """
    return _vis(lat=lat, lon=lon, kp=kp).model_dump()


@mcp.tool()
def compute_drag_delta_tool(altitude_km: float, kp: float) -> dict[str, Any]:
    """Atmospheric drag delta-v fraction for an LEO altitude during a storm."""
    return compute_drag_delta(altitude_km=altitude_km, kp=kp).model_dump()


@mcp.tool()
def retrieve_context(query: str, k: int = 5, persona: str = "") -> list[dict[str, Any]]:
    """Semantic search over AuroraGaze's curated event corpus.

    Persona is one of {"aurora", "satellite", ""}; empty matches both.
    """
    chunks = retrieve(query=query, k=k, persona=persona or None)
    return [c.model_dump(mode="json") for c in chunks]


@mcp.tool()
async def nearby_viewing_spots(
    lat: float,
    lon: float,
    radius_km: int = 50,
    location: str = "",
) -> list[dict[str, Any]]:
    """Ranked aurora viewing spots inside a chaser's drive radius (5..300 km).

    Surveys OpenStreetMap viewpoints, peaks, and reserves around the base,
    scores each by geomagnetic latitude vs Kp boundary, cloud forecast for
    tonight's window, light-pollution proxy, and drive-distance penalty.
    Returns up to 25 spots best-first; the user's base location is always
    included so chasers can compare staying put with driving out.
    """
    radius_km = max(5, min(300, int(radius_km)))
    request_utc = datetime.now(UTC)
    night = local_night(lat=lat, lon=lon, request_utc=request_utc, location_label=location)
    async with httpx.AsyncClient(timeout=12.0) as client:
        try:
            forecast = await get_kp_forecast(client)
        except Exception:
            kp = await _kp(client)
            forecast = forecast_from_current(kp)
        candidates = await find_candidate_spots(
            lat, lon, radius_km, base_name=location or "base", client=client
        )
        places = await find_populated_places(
            lat, lon, min(400, radius_km + 60), client=client
        )
        coords = [(c.lat, c.lon) for c in candidates]
        cloud_lookup = await cloud_cover_for_window(coords, night, client=client)
    bortle_lookup = {
        (round(c.lat, 3), round(c.lon, 3)): bortle_at(c.lat, c.lon, places) for c in candidates
    }
    ranked = rank_spots(
        base_lat=lat,
        candidates=candidates,
        night=night,
        bins=list(forecast.bins),
        cloud_lookup=cloud_lookup,
        bortle_lookup=bortle_lookup,
    )
    return [r.model_dump(mode="json") for r in ranked]


def main() -> None:
    asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main()
