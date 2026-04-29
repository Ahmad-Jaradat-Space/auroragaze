"""Six-node LangGraph for AuroraGaze.

supervisor -> (data_fetcher || retrieval) -> physics -> composer

The composer chooses an aurora or satellite path from `state["persona"]`.
Each node is a plain function that returns a partial state update.
"""

import json
from datetime import UTC, datetime
from typing import Any

import httpx
from langgraph.graph import END, START, StateGraph

from auroragaze.agents.prompts import AURORA_SYSTEM, SATELLITE_SYSTEM, VERIFIER_RETRY_HINT
from auroragaze.agents.verifier import verify_briefing
from auroragaze.llm import make_llm
from auroragaze.retrieval.retriever import retrieve
from auroragaze.schemas import (
    AuroraBriefing,
    BriefingState,
    Citation,
    NightWindow,
    SatelliteBriefing,
    Visibility,
    VisibilityWindow,
)
from auroragaze.tools.dst import get_dst_now
from auroragaze.tools.fleet import FleetUnit, assess_fleet_impact
from auroragaze.tools.kp import get_kp_now
from auroragaze.tools.kp_forecast import forecast_from_current, get_kp_forecast
from auroragaze.tools.night import local_night
from auroragaze.tools.physics import assess_visibility, visibility_for_window
from auroragaze.tools.solar_wind import get_solar_wind
from auroragaze.tools.xray import get_goes_xray


def _trace(state: BriefingState, line: str) -> list[str]:
    return [line]


def supervisor_node(state: BriefingState) -> dict[str, Any]:
    persona = state.get("persona", "aurora")
    request_utc = datetime.now(UTC)
    update: dict[str, Any] = {"request_time_utc": request_utc}
    if persona == "aurora":
        loc = state.get("location_label", f"({state.get('lat')}, {state.get('lon')})")
        query = f"southern hemisphere aurora visibility from {loc} during a geomagnetic storm"
        # Compute the local night window for the upcoming evening at this location.
        nw = local_night(
            lat=state.get("lat", -42.88),
            lon=state.get("lon", 147.32),
            request_utc=request_utc,
            location_label=loc,
        )
        update["night_window"] = nw
        update["query"] = query
        line = (
            f"supervisor: persona=aurora location={loc!r} "
            f"night={nw.astro_night_start_local or nw.sunset_local}→"
            f"{nw.astro_night_end_local or nw.sunrise_local} ({nw.timezone})"
        )
    else:
        update["query"] = "satellite operator briefing storm impact drag fleet"
        line = f"supervisor: persona=satellite query={update['query']!r}"
    update["trace"] = _trace(state, line)
    return update


async def data_fetcher_node(state: BriefingState) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        sw = await get_solar_wind(client)
        kp = await get_kp_now(client)
        try:
            dst = await get_dst_now(client)
            dst_val = dst.dst_nt
        except Exception:
            dst_val = 0.0
        try:
            xray = await get_goes_xray(client)
            flare = xray.flare_class
        except Exception:
            flare = "A"
        try:
            forecast = await get_kp_forecast(client)
        except Exception:
            forecast = forecast_from_current(kp)
    line = (
        f"data_fetcher: Bz={sw.bz:.1f}nT v={sw.speed_kms:.0f}km/s "
        f"Kp={kp.kp:.1f} Dst={dst_val:.0f}nT flare={flare} "
        f"forecast_bins={len(forecast.bins)} "
        f"[{sw.timestamp.isoformat(timespec='minutes')}]"
    )
    return {
        "solar_wind": sw,
        "kp": kp,
        "dst_nt": dst_val,
        "flare_class": flare,
        "kp_forecast": forecast,
        "trace": _trace(state, line),
    }


_ORBIT_QUERY = {
    "LEO_low": "atmospheric drag thermospheric density at low LEO {alt}km during geomagnetic storm",
    "LEO_mid": "atmospheric drag at LEO {alt}km during geomagnetic storm fleet operations",
    "LEO_high": "high-LEO operations and surface charging during geomagnetic storm",
    "MEO": "MEO GNSS single-event upset surface charging during geomagnetic storm",
    "GEO": "geosynchronous satellite surface charging deep dielectric storm anomaly",
}


def _satellite_subqueries(state: BriefingState) -> list[str]:
    fleet_raw = state.get("fleet", []) or []
    classes_seen: list[str] = []
    queries: list[str] = []
    for u in fleet_raw:
        cls = str(u.get("orbit_class", ""))
        if cls in _ORBIT_QUERY and cls not in classes_seen:
            classes_seen.append(cls)
            alt = u.get("altitude_km", 0)
            queries.append(_ORBIT_QUERY[cls].format(alt=int(alt) if alt else ""))
    if not queries:
        queries = [state.get("query", "satellite operator briefing storm impact")]
    return queries


def retrieval_node(state: BriefingState) -> dict[str, Any]:
    persona = state.get("persona", "aurora")
    if persona == "satellite":
        seen: dict[str, Any] = {}
        for q in _satellite_subqueries(state):
            for c in retrieve(query=q, k=4, persona=persona):
                if c.source not in seen:
                    seen[c.source] = c
                if len(seen) >= 6:
                    break
            if len(seen) >= 6:
                break
        chunks = list(seen.values())[:6]
        summary = ", ".join(c.source.split("/")[-1][:40] for c in chunks[:3])
        return {
            "chunks": chunks,
            "trace": _trace(
                state,
                f"retrieval: {len(chunks)} chunks via {len(_satellite_subqueries(state))} sub-queries ({summary})",
            ),
        }
    query = state.get("query", "")
    chunks = retrieve(query=query, k=5, persona=persona)
    summary = ", ".join(c.source.split("/")[-1][:40] for c in chunks[:3])
    return {
        "chunks": chunks,
        "trace": _trace(state, f"retrieval: {len(chunks)} chunks ({summary})"),
    }


def physics_node(state: BriefingState) -> dict[str, Any]:
    persona = state.get("persona", "aurora")
    kp = state.get("kp")
    if kp is None:
        return {"trace": _trace(state, "physics: skipped (no kp)")}
    if persona == "aurora":
        lat = state.get("lat", -42.88)
        lon = state.get("lon", 147.32)
        nw: NightWindow | None = state.get("night_window")
        forecast = state.get("kp_forecast")
        bins = list(forecast.bins) if forecast else []
        if nw is not None and bins:
            vw = visibility_for_window(lat=lat, lon=lon, night=nw, bins=bins)
            v = vw.night
            line = (
                f"physics: night {vw.summary_window}; peak Kp={vw.peak_kp:.1f} "
                f"@ {vw.peak_local} → {vw.headline_level}"
            )
            return {
                "visibility": v,
                "visibility_window": vw,
                "trace": _trace(state, line),
            }
        # fallback: single-shot visibility from current Kp
        v = assess_visibility(lat=lat, lon=lon, kp=kp.kp)
        line = (
            f"physics: oval threshold ~{v.boundary_lat_deg:.1f}°S; "
            f"viewer {abs(lat):.1f}°S → {v.level} (single-shot)"
        )
        return {"visibility": v, "trace": _trace(state, line)}
    fleet_raw = state.get("fleet", [])
    fleet = [FleetUnit.model_validate(u) for u in fleet_raw] if fleet_raw else []
    if not fleet:
        return {"trace": _trace(state, "physics: no fleet config provided")}
    impact = assess_fleet_impact(fleet=fleet, kp=kp.kp)
    return {
        "fleet_impact": impact.model_dump(),
        "trace": _trace(state, f"physics: fleet headline → {impact.headline}"),
    }


def _format_chunks(chunks: list[Any]) -> str:
    parts = []
    for i, c in enumerate(chunks, start=1):
        head = c.source
        if c.event_date:
            head = f"{c.event_date} — {head}"
        parts.append(f"[{i}] {head}\n{c.text[:600]}")
    return "\n\n".join(parts)


async def aurora_composer_node(state: BriefingState) -> dict[str, Any]:
    sw = state["solar_wind"]
    kp = state["kp"]
    visibility: Visibility = state["visibility"]
    chunks = state.get("chunks", [])
    location = state.get("location_label", f"({state.get('lat')}, {state.get('lon')})")
    nw: NightWindow | None = state.get("night_window")
    vw: VisibilityWindow | None = state.get("visibility_window")
    retry_hint = state.get("retry_hint", "")

    night_block = ""
    if nw is not None:
        night_block = (
            f"Night window for tonight at this location ({nw.timezone}):\n"
            f"  sunset       = {nw.sunset_local}\n"
            f"  civil dusk   = {nw.civil_dusk_local}\n"
            f"  astro night  = {nw.astro_night_start_local} → {nw.astro_night_end_local}\n"
            f"  civil dawn   = {nw.civil_dawn_local}\n"
            f"  sunrise      = {nw.sunrise_local}\n"
            f"  request_in_daylight = {nw.is_daylight_now}\n"
        )
    window_block = ""
    if vw is not None:
        window_block = (
            "Forecast visibility per sub-window:\n"
            f"  evening: level={vw.evening.level}\n"
            f"  night:   level={vw.night.level}  (HEADLINE)\n"
            f"  dawn:    level={vw.dawn.level}\n"
            f"  peak forecast Kp = {vw.peak_kp:.2f} at {vw.peak_local}\n"
            f"  best-time bracket = {vw.summary_window}\n"
        )

    user_msg = (
        f"Location: {location}\n"
        f"Observed now: Bz={sw.bz:.1f}nT, v={sw.speed_kms:.0f}km/s, "
        f"density={sw.density_cm3:.1f}cm-3, Kp={kp.kp:.1f} "
        f"({sw.timestamp.isoformat(timespec='minutes')}).\n"
        f"{night_block}{window_block}"
        f"Computed visibility (night block): level={visibility.level}, "
        f"oval threshold ~{visibility.boundary_lat_deg:.1f}°S.\n\n"
        f"Reference chunks:\n{_format_chunks(chunks)}\n\n"
        "Write the AuroraBriefing as JSON matching the AuroraBriefing schema. "
        "Required fields: summary, location, when_local, visibility, "
        "viewing_window, headline, body, citations. "
        "The when_local string must quote the night window's bracket exactly."
        + (f"\n\n{retry_hint}" if retry_hint else "")
    )
    llm = make_llm()
    structured = llm.with_structured_output(AuroraBriefing)
    briefing = await structured.ainvoke(
        [{"role": "system", "content": AURORA_SYSTEM}, {"role": "user", "content": user_msg}]
    )
    if not isinstance(briefing, AuroraBriefing):
        briefing = AuroraBriefing.model_validate(briefing)
    if not briefing.citations:
        briefing = briefing.model_copy(
            update={
                "citations": [
                    Citation(
                        source=chunks[0].source if chunks else "NOAA SWPC",
                        detail="reference event",
                    )
                ]
            }
        )
    return {"briefing": briefing, "trace": _trace(state, "composer: aurora briefing ready")}


async def satellite_composer_node(state: BriefingState) -> dict[str, Any]:
    sw = state["solar_wind"]
    kp = state["kp"]
    chunks = state.get("chunks", [])
    fleet_impact = state.get("fleet_impact", {})
    fleet_label = state.get("fleet_label", "fleet")
    retry_hint = state.get("retry_hint", "")
    user_msg = (
        f"Fleet: {fleet_label}\n"
        f"Now: Bz={sw.bz:.1f}nT, v={sw.speed_kms:.0f}km/s, "
        f"Kp={kp.kp:.1f}, Dst={state.get('dst_nt', 0):.0f}nT, "
        f"flare class={state.get('flare_class', 'A')} "
        f"(observed {sw.timestamp.isoformat(timespec='minutes')}).\n"
        f"Computed fleet impact: {json.dumps(fleet_impact)[:1500]}\n\n"
        f"Reference chunks:\n{_format_chunks(chunks)}\n\n"
        "Write the SatelliteBriefing as JSON: "
        "{summary, fleet_label, storm_summary, headline, body, per_unit_actions:[...], "
        "citations:[{source,detail}]}." + (f"\n\n{retry_hint}" if retry_hint else "")
    )
    llm = make_llm()
    structured = llm.with_structured_output(SatelliteBriefing)
    briefing = await structured.ainvoke(
        [{"role": "system", "content": SATELLITE_SYSTEM}, {"role": "user", "content": user_msg}]
    )
    if not isinstance(briefing, SatelliteBriefing):
        briefing = SatelliteBriefing.model_validate(briefing)
    if not briefing.citations:
        briefing = briefing.model_copy(
            update={
                "citations": [
                    Citation(
                        source=chunks[0].source if chunks else "NOAA SWPC",
                        detail="reference event",
                    )
                ]
            }
        )
    return {"briefing": briefing, "trace": _trace(state, "composer: satellite briefing ready")}


def verifier_node(state: BriefingState) -> dict[str, Any]:
    """Reject the briefing if any number is unsupported by tools or chunks.

    On rejection, builds a retry hint and clears the briefing so the
    conditional edge sends control back to the matching composer once.
    """
    briefing = state.get("briefing")
    if briefing is None:
        return {"trace": _trace(state, "verifier: no briefing to check")}
    text = " ".join(
        [
            getattr(briefing, "summary", "") or "",
            getattr(briefing, "headline", "") or "",
            getattr(briefing, "body", "") or "",
            getattr(briefing, "storm_summary", "") or "",
        ]
    )
    unsupported = verify_briefing(text, dict(state))
    retry_count = int(state.get("retry_count", 0))
    if not unsupported:
        return {"trace": _trace(state, "verifier: grounded ✓")}
    if retry_count >= 1:
        return {
            "trace": _trace(
                state,
                f"verifier: {len(unsupported)} unsupported number(s) "
                f"({unsupported[:3]}) — retry exhausted, accepting",
            )
        }
    hint = VERIFIER_RETRY_HINT.format(unsupported=", ".join(str(n) for n in unsupported))
    return {
        "briefing": None,
        "retry_hint": hint,
        "retry_count": retry_count + 1,
        "trace": _trace(
            state, f"verifier: rejected — {len(unsupported)} unsupported, retrying composer"
        ),
    }


def _route_composer(state: BriefingState) -> str:
    return "aurora_composer" if state.get("persona", "aurora") == "aurora" else "satellite_composer"


def _route_after_verifier(state: BriefingState) -> str:
    if state.get("briefing") is not None:
        return "end"
    persona = state.get("persona", "aurora")
    return "aurora_composer" if persona == "aurora" else "satellite_composer"


def build_graph() -> Any:
    g = StateGraph(BriefingState)
    g.add_node("supervisor", supervisor_node)
    g.add_node("data_fetcher", data_fetcher_node)
    g.add_node("retrieval", retrieval_node)
    g.add_node("physics", physics_node)
    g.add_node("aurora_composer", aurora_composer_node)
    g.add_node("satellite_composer", satellite_composer_node)
    g.add_node("verifier", verifier_node)

    g.add_edge(START, "supervisor")
    g.add_edge("supervisor", "data_fetcher")
    g.add_edge("supervisor", "retrieval")
    g.add_edge("data_fetcher", "physics")
    g.add_edge("retrieval", "physics")
    g.add_conditional_edges(
        "physics",
        _route_composer,
        {"aurora_composer": "aurora_composer", "satellite_composer": "satellite_composer"},
    )
    g.add_edge("aurora_composer", "verifier")
    g.add_edge("satellite_composer", "verifier")
    g.add_conditional_edges(
        "verifier",
        _route_after_verifier,
        {
            "aurora_composer": "aurora_composer",
            "satellite_composer": "satellite_composer",
            "end": END,
        },
    )
    return g.compile()


graph = build_graph()
