"""MCP server for AuroraGaze.

Exposes six tools to any MCP client (Claude Desktop, Cursor, internal ops):

- get_solar_wind        — live DSCOVR Bz / speed / density
- get_kp_now            — current planetary Kp
- get_dst_now           — current Dst
- assess_visibility     — auroral visibility for a location at given Kp
- compute_drag_delta    — atmospheric drag fraction for an LEO altitude + Kp
- retrieve_context      — semantic search over the curated event corpus

Run with: `python -m auroragaze.mcp_server.server`
Test with: `mcp dev src/auroragaze/mcp_server/server.py`
"""

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP

from auroragaze.retrieval.retriever import retrieve
from auroragaze.tools.drag import compute_drag_delta
from auroragaze.tools.dst import get_dst_now as _dst
from auroragaze.tools.kp import get_kp_now as _kp
from auroragaze.tools.physics import assess_visibility as _vis
from auroragaze.tools.solar_wind import get_solar_wind as _sw

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


def main() -> None:
    asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main()
