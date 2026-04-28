import pytest
from pytest_httpx import HTTPXMock

from auroragaze.tools.kp import KP_URL, get_kp_now

_KP_PAYLOAD = [
    ["time_tag", "kp", "a_running", "station_count"],
    ["2026-04-29 12:00:00.000", "4.33", "20", "10"],
    ["2026-04-29 15:00:00.000", "6.20", "32", "10"],
]


@pytest.mark.asyncio
async def test_get_kp_now_parses_last(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=KP_URL, json=_KP_PAYLOAD)
    kp = await get_kp_now()
    assert kp.kp == 6.20
    assert kp.timestamp.isoformat().startswith("2026-04-29T15:00:00")
