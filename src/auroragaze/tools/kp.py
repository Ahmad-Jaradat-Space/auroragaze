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

    # data[0] is the header; rows are [time_tag, kp, a_running, station_count]
    last = data[-1]
    ts = datetime.fromisoformat(last[0].replace(" ", "T")).replace(tzinfo=UTC)
    return KpReading(kp=float(last[1]), timestamp=ts)
