import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auroragaze.graph import graph
from auroragaze.tools.kp import get_kp_now
from auroragaze.tools.solar_wind import get_solar_wind

router = APIRouter()


class AuroraRequest(BaseModel):
    lat: float
    lon: float
    location: str = ""


class FleetUnitInput(BaseModel):
    name: str
    altitude_km: float
    orbit_class: str
    hardness: str = "standard"
    mission: str = "communications"


class SatelliteRequest(BaseModel):
    fleet_label: str
    fleet: list[FleetUnitInput]


@router.get("/snapshot")
async def snapshot() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        sw = await get_solar_wind(client)
        kp = await get_kp_now(client)
    return {"solar_wind": sw.model_dump(mode="json"), "kp": kp.model_dump(mode="json")}


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


async def _stream_aurora(req: AuroraRequest) -> AsyncIterator[str]:
    state = {
        "persona": "aurora",
        "lat": req.lat,
        "lon": req.lon,
        "location_label": req.location or f"({req.lat:.2f}, {req.lon:.2f})",
    }
    seen = 0
    final: dict[str, Any] = {}
    async for event in graph.astream(state, stream_mode="values"):
        trace = event.get("trace", [])
        while seen < len(trace):
            yield _sse({"type": "step", "line": trace[seen]})
            seen += 1
        final = event
    briefing = final.get("briefing")
    if briefing is not None:
        yield _sse({"type": "briefing", "briefing": briefing.model_dump(mode="json")})
    yield _sse({"type": "done"})


async def _stream_satellite(req: SatelliteRequest) -> AsyncIterator[str]:
    state = {
        "persona": "satellite",
        "fleet_label": req.fleet_label,
        "fleet": [u.model_dump() for u in req.fleet],
    }
    seen = 0
    final: dict[str, Any] = {}
    async for event in graph.astream(state, stream_mode="values"):
        trace = event.get("trace", [])
        while seen < len(trace):
            yield _sse({"type": "step", "line": trace[seen]})
            seen += 1
        final = event
    briefing = final.get("briefing")
    if briefing is not None:
        yield _sse({"type": "briefing", "briefing": briefing.model_dump(mode="json")})
    yield _sse({"type": "done"})


@router.post("/brief/aurora")
async def brief_aurora(req: AuroraRequest) -> StreamingResponse:
    return StreamingResponse(_stream_aurora(req), media_type="text/event-stream")


@router.post("/brief/satellite")
async def brief_satellite(req: SatelliteRequest) -> StreamingResponse:
    return StreamingResponse(_stream_satellite(req), media_type="text/event-stream")
