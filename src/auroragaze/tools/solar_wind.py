from datetime import UTC, datetime

import httpx

from auroragaze.schemas import SolarWind

MAG_URL = "https://services.swpc.noaa.gov/products/solar-wind/mag-5-minute.json"
PLASMA_URL = "https://services.swpc.noaa.gov/products/solar-wind/plasma-5-minute.json"


def _last_row(rows: list[list[str]]) -> list[str]:
    return rows[-1]


async def get_solar_wind(client: httpx.AsyncClient | None = None) -> SolarWind:
    own_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=10.0)
    try:
        mag = (await client.get(MAG_URL)).json()
        plasma = (await client.get(PLASMA_URL)).json()
    finally:
        if own_client:
            await client.aclose()

    # NOAA returns [header, row1, row2, ...]; last row is most recent.
    mag_row = _last_row(mag[1:])
    plasma_row = _last_row(plasma[1:])
    # mag header: time_tag, bx_gsm, by_gsm, bz_gsm, lon_gsm, lat_gsm, bt
    # plasma header: time_tag, density, speed, temperature
    ts = datetime.fromisoformat(mag_row[0].replace(" ", "T")).replace(tzinfo=UTC)
    return SolarWind(
        bz=float(mag_row[3]),
        bt=float(mag_row[6]),
        speed_kms=float(plasma_row[2]),
        density_cm3=float(plasma_row[1]),
        timestamp=ts,
    )
