import pytest
from pytest_httpx import HTTPXMock

from auroragaze.tools.solar_wind import MAG_URL, PLASMA_URL, get_solar_wind

_MAG_PAYLOAD = [
    ["time_tag", "bx_gsm", "by_gsm", "bz_gsm", "lon_gsm", "lat_gsm", "bt"],
    ["2026-04-29 14:25:00.000", "1.0", "2.0", "-12.5", "0.0", "0.0", "13.0"],
    ["2026-04-29 14:30:00.000", "1.1", "2.1", "-11.8", "0.0", "0.0", "12.5"],
]

_PLASMA_PAYLOAD = [
    ["time_tag", "density", "speed", "temperature"],
    ["2026-04-29 14:25:00.000", "7.2", "640.0", "180000"],
    ["2026-04-29 14:30:00.000", "8.1", "680.0", "190000"],
]


@pytest.mark.asyncio
async def test_get_solar_wind_parses_last_row(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=MAG_URL, json=_MAG_PAYLOAD)
    httpx_mock.add_response(url=PLASMA_URL, json=_PLASMA_PAYLOAD)
    sw = await get_solar_wind()
    assert sw.bz == -11.8
    assert sw.bt == 12.5
    assert sw.speed_kms == 680.0
    assert sw.density_cm3 == 8.1
    assert sw.timestamp.isoformat().startswith("2026-04-29T14:30:00")
