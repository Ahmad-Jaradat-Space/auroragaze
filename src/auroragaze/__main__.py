import argparse
import asyncio
import json

from auroragaze.graph import graph


async def _run_aurora(lat: float, lon: float, location: str) -> None:
    state = {"persona": "aurora", "lat": lat, "lon": lon, "location_label": location}
    out = await graph.ainvoke(state)
    for line in out.get("trace", []):
        print(line)
    briefing = out.get("briefing")
    if briefing is not None:
        print()
        print(json.dumps(briefing.model_dump(), indent=2, default=str))


async def _run_satellite(fleet_path: str, label: str) -> None:
    with open(fleet_path) as f:
        fleet = json.load(f)
    state = {"persona": "satellite", "fleet": fleet, "fleet_label": label}
    out = await graph.ainvoke(state)
    for line in out.get("trace", []):
        print(line)
    briefing = out.get("briefing")
    if briefing is not None:
        print()
        print(json.dumps(briefing.model_dump(), indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(prog="auroragaze")
    sub = parser.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("brief")
    a.add_argument("--lat", type=float, required=True)
    a.add_argument("--lon", type=float, required=True)
    a.add_argument("--location", default="")
    s = sub.add_parser("fleet-brief")
    s.add_argument("--fleet", required=True, help="path to JSON list of fleet units")
    s.add_argument("--label", default="fleet")
    args = parser.parse_args()
    if args.cmd == "brief":
        asyncio.run(_run_aurora(args.lat, args.lon, args.location or f"({args.lat},{args.lon})"))
    elif args.cmd == "fleet-brief":
        asyncio.run(_run_satellite(args.fleet, args.label))


if __name__ == "__main__":
    main()
