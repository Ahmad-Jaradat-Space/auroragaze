import pytest
from pytest_httpx import HTTPXMock

from auroragaze.tools.kp_forecast import FORECAST_URL, get_kp_forecast

_PAYLOAD = [
    {"time_tag": "2026-04-29T06:00:00", "kp": 2.0, "observed": "observed", "noaa_scale": None},
    {"time_tag": "2026-04-29T09:00:00", "kp": 4.67, "observed": "predicted", "noaa_scale": None},
    {"time_tag": "2026-04-29T12:00:00", "kp": 6.0, "observed": "predicted", "noaa_scale": None},
]


@pytest.mark.asyncio
async def test_parses_noaa_forecast_payload(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=FORECAST_URL, json=_PAYLOAD)
    f = await get_kp_forecast()
    assert len(f.bins) == 3
    assert f.bins[0].kp == 2.0
    assert f.bins[2].kp == 6.0
    # 3-hour bins
    assert (f.bins[0].end - f.bins[0].start).total_seconds() == 3 * 3600


@pytest.mark.asyncio
async def test_empty_response_yields_fallback(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=FORECAST_URL, json=[])
    f = await get_kp_forecast()
    assert "fallback" in f.source
    assert len(f.bins) == 1
    assert f.bins[0].kp == 1.0


@pytest.mark.asyncio
async def test_bad_payload_yields_fallback(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url=FORECAST_URL, status_code=500, text="server error")
    f = await get_kp_forecast()
    assert "fallback" in f.source
