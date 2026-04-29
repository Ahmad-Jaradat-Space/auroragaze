from datetime import UTC, datetime

from auroragaze.tools.night import local_night


def test_hobart_april_evening_window() -> None:
    # Hobart, April 29 — sunset ~17:30 AEST, sunrise next day ~06:50 AEST.
    nw = local_night(
        lat=-42.88,
        lon=147.32,
        request_utc=datetime(2026, 4, 29, 4, 0, tzinfo=UTC),  # 14:00 AEST
        location_label="Hobart, TAS",
    )
    assert nw.timezone == "Australia/Hobart"
    # Sunset should be late afternoon in April; tolerate ±90 min.
    sset_h = int(nw.sunset_local.split(":")[0])
    assert 16 <= sset_h <= 19
    sris_h = int(nw.sunrise_local.split(":")[0])
    assert 5 <= sris_h <= 8
    assert nw.civil_dusk_local is not None
    assert nw.astro_night_start_local is not None


def test_melbourne_window_returns_string() -> None:
    nw = local_night(
        lat=-37.81,
        lon=144.96,
        request_utc=datetime(2026, 6, 21, 4, 0, tzinfo=UTC),
        location_label="Melbourne, VIC",
    )
    assert nw.timezone == "Australia/Melbourne"
    assert ":" in nw.sunset_local
    assert ":" in nw.sunrise_local
    assert nw.is_daylight_now is True  # 14:00 local in winter is mid-afternoon


def test_request_during_night_flags_not_daylight() -> None:
    # 13:00 UTC on June 21 = 23:00 AEST in Hobart — middle of the night
    nw = local_night(
        lat=-42.88,
        lon=147.32,
        request_utc=datetime(2026, 6, 21, 13, 0, tzinfo=UTC),
        location_label="Hobart, TAS",
    )
    assert nw.is_daylight_now is False


def test_polar_fallback_does_not_crash() -> None:
    # 89°S in mid-summer (Antarctic): no sunset event possible
    nw = local_night(
        lat=-89.0,
        lon=0.0,
        request_utc=datetime(2026, 12, 21, 12, 0, tzinfo=UTC),
        tz_name="Etc/UTC",
    )
    assert nw.sunrise_utc > nw.sunset_utc
