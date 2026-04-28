from datetime import UTC, datetime

import httpx
from pydantic import BaseModel

XRAY_URL = "https://services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json"


class XrayReading(BaseModel):
    flux_long: float
    flux_short: float
    flare_class: str
    timestamp: datetime
    source: str = "GOES primary X-ray sensor (1-minute averages)"


def _flare_class(flux_long: float) -> str:
    if flux_long < 1e-7:
        return "A"
    if flux_long < 1e-6:
        return "B"
    if flux_long < 1e-5:
        return "C"
    if flux_long < 1e-4:
        return "M"
    return "X"


async def get_goes_xray(client: httpx.AsyncClient | None = None) -> XrayReading:
    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=10.0)
    try:
        data = (await client.get(XRAY_URL)).json()
    finally:
        if own_client:
            await client.aclose()
    long_rows = [r for r in data if r.get("energy") == "0.1-0.8nm"]
    short_rows = [r for r in data if r.get("energy") == "0.05-0.4nm"]
    long_last = long_rows[-1]
    short_last = short_rows[-1]
    ts = datetime.fromisoformat(long_last["time_tag"].replace("Z", "+00:00")).astimezone(UTC)
    fl = float(long_last["flux"])
    return XrayReading(
        flux_long=fl,
        flux_short=float(short_last["flux"]),
        flare_class=_flare_class(fl),
        timestamp=ts,
    )
