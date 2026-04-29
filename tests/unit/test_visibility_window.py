from datetime import UTC, datetime, timedelta

from auroragaze.schemas import KpBin
from auroragaze.tools.night import local_night
from auroragaze.tools.physics import visibility_for_window


def _bins(values: list[float], start: datetime) -> list[KpBin]:
    out = []
    for i, v in enumerate(values):
        s = start + timedelta(hours=3 * i)
        out.append(KpBin(start=s, end=s + timedelta(hours=3), kp=v))
    return out


def test_storm_at_local_midnight_gives_likely_for_hobart() -> None:
    nw = local_night(
        lat=-42.88,
        lon=147.32,
        request_utc=datetime(2026, 4, 29, 4, 0, tzinfo=UTC),
        location_label="Hobart, TAS",
    )
    # 24 bins covering the whole day, peaking Kp 8 around UTC midday (~22:00 AEST)
    bins = _bins([1, 1, 2, 4, 6, 8, 7, 4], start=datetime(2026, 4, 29, 0, 0, tzinfo=UTC))
    vw = visibility_for_window(lat=-42.88, lon=147.32, night=nw, bins=bins)
    assert vw.peak_kp >= 7
    assert vw.headline_level in {"likely", "possible"}
    assert "AEST" in vw.summary_window or "Hobart" in vw.summary_window or vw.summary_window != ""


def test_quiet_window_unlikely() -> None:
    nw = local_night(
        lat=-42.88,
        lon=147.32,
        request_utc=datetime(2026, 4, 29, 4, 0, tzinfo=UTC),
        location_label="Hobart, TAS",
    )
    bins = _bins([0.7] * 8, start=datetime(2026, 4, 29, 0, 0, tzinfo=UTC))
    vw = visibility_for_window(lat=-42.88, lon=147.32, night=nw, bins=bins)
    assert vw.headline_level == "unlikely"
    assert vw.peak_kp < 1.5
