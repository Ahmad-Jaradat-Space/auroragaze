"""Run the graph against the golden set and write per-event results.

The graph normally hits live NOAA. For deterministic eval we monkeypatch
the data tools to return the canned values from each golden-set entry, so
the same query always sees the same Bz/Kp/speed/density.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from auroragaze.graph import graph
from auroragaze.schemas import KpReading, SolarWind
from auroragaze.tools import dst as dst_mod
from auroragaze.tools import kp as kp_mod
from auroragaze.tools import solar_wind as sw_mod
from auroragaze.tools import xray as xray_mod
from auroragaze.tools.dst import DstReading
from auroragaze.tools.xray import XrayReading

ROOT = Path(__file__).resolve().parent
GOLDEN = ROOT / "golden_set.jsonl"


def _patch_tools(event: dict[str, Any]) -> None:
    ts = datetime.fromisoformat(event["date"].replace("Z", "+00:00"))
    sw = SolarWind(
        bz=event["bz"],
        bt=abs(event["bz"]) + 1.0,
        speed_kms=event["speed_kms"],
        density_cm3=event["density_cm3"],
        timestamp=ts,
        source=f"GOLDEN[{event['event_id']}]",
    )
    kp = KpReading(kp=event["kp"], timestamp=ts, source=f"GOLDEN[{event['event_id']}]")
    dst = DstReading(dst_nt=-100.0 if event["kp"] >= 6 else 0.0, timestamp=ts)
    xray = XrayReading(flux_long=1e-6, flux_short=1e-7, flare_class="C", timestamp=ts)

    async def fake_sw(client: Any = None) -> SolarWind:
        return sw

    async def fake_kp(client: Any = None) -> KpReading:
        return kp

    async def fake_dst(client: Any = None) -> DstReading:
        return dst

    async def fake_xray(client: Any = None) -> XrayReading:
        return xray

    sw_mod.get_solar_wind = fake_sw
    kp_mod.get_kp_now = fake_kp
    dst_mod.get_dst_now = fake_dst
    xray_mod.get_goes_xray = fake_xray
    # also patch the references already imported in graph.py
    import auroragaze.graph as g

    g.get_solar_wind = fake_sw
    g.get_kp_now = fake_kp
    g.get_dst_now = fake_dst
    g.get_goes_xray = fake_xray


async def _run_one(event: dict[str, Any]) -> dict[str, Any]:
    _patch_tools(event)
    if event["persona"] == "aurora":
        state = {
            "persona": "aurora",
            "lat": event["lat"],
            "lon": event["lon"],
            "location_label": event["location"],
        }
    else:
        state = {
            "persona": "satellite",
            "fleet_label": event["fleet_label"],
            "fleet": event["fleet"],
        }
    out = await graph.ainvoke(state)
    briefing = out.get("briefing")
    return {
        "event_id": event["event_id"],
        "persona": event["persona"],
        "expected": {k: v for k, v in event.items() if k.startswith("expected_")},
        "trace": out.get("trace", []),
        "briefing": briefing.model_dump(mode="json") if briefing is not None else None,
    }


async def main(out_path: Path) -> None:
    events = [json.loads(line) for line in GOLDEN.read_text().splitlines() if line.strip()]
    results: list[dict[str, Any]] = []
    for ev in events:
        print(f"running {ev['event_id']}...")
        try:
            r = await _run_one(ev)
        except Exception as exc:
            r = {"event_id": ev["event_id"], "error": str(exc)}
            print(f"  ERROR: {exc}")
        results.append(r)
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nwrote {len(results)} results to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "results.json"))
    args = parser.parse_args()
    asyncio.run(main(Path(args.out)))
