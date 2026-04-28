from datetime import UTC, datetime

import httpx
from pydantic import BaseModel

KYOTO_URL = "https://services.swpc.noaa.gov/products/kyoto-dst.json"


class DstReading(BaseModel):
    dst_nt: float
    timestamp: datetime
    source: str = "Kyoto WDC / NOAA SWPC mirror (provisional)"


async def get_dst_now(client: httpx.AsyncClient | None = None) -> DstReading:
    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=10.0)
    try:
        data = (await client.get(KYOTO_URL)).json()
    finally:
        if own_client:
            await client.aclose()
    last = data[-1]
    ts = datetime.fromisoformat(last[0].replace(" ", "T")).replace(tzinfo=UTC)
    return DstReading(dst_nt=float(last[1]), timestamp=ts)
