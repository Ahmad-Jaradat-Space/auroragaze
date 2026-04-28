from datetime import UTC, datetime

import httpx

from auroragaze.schemas import KpReading

KP_URL = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"


async def get_kp_now(client: httpx.AsyncClient | None = None) -> KpReading:
    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=10.0)
    try:
        data = (await client.get(KP_URL)).json()
    finally:
        if own_client:
            await client.aclose()

    last = data[-1]
    ts_raw = last["time_tag"].replace(" ", "T").rstrip("Z")
    ts = datetime.fromisoformat(ts_raw).replace(tzinfo=UTC)
    return KpReading(kp=float(last["Kp"]), timestamp=ts)
