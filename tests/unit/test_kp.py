import pytest
from pytest_httpx import HTTPXMock

from auroragaze.tools.kp import KP_URL, get_kp_now

_KP_PAYLOAD = [
    {"time_tag": "2026-04-29T12:00:00", "Kp": 4.33, "a_running": 20, "station_count": 8},
    {"time_tag": "2026-04-29T15:00:00", "Kp": 6.20, "a_running": 32, "station_count": 8},
]


@pytest.mark.asyncio
async def test_get_kp_now_parses_last(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=KP_URL, json=_KP_PAYLOAD)
    kp = await get_kp_now()
    assert kp.kp == 6.20
    assert kp.timestamp.isoformat().startswith("2026-04-29T15:00:00")
