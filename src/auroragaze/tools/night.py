"""Local night window — sunrise, sunset, civil and astronomical twilight.

Pure Python; no external dependency. Uses the standard NOAA solar-position
algorithm (declination, hour angle, equation of time) which is accurate to
better than ~2 minutes at temperate southern latitudes — adequate for the
"tonight ~21:30 to 03:10" briefings AuroraGaze produces.

Function: `local_night(lat, lon, on_date_utc, tz_name) -> NightWindow`.

For viewing locations whose timezone is known by the caller (the city
dropdown supplies them), pass `tz_name`. For arbitrary lat/lon we fall back
to a longitude-derived UTC offset (15° per hour) — coarse but always works.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from auroragaze.schemas import NightWindow

# Solar elevation thresholds for each event, degrees (positive = above horizon)
_SUN_ALT = {
    "sunset": -0.833,  # standard refraction-corrected sunset
    "civil": -6.0,  # civil twilight
    "astro": -18.0,  # astronomical twilight (true night)
}


def _julian_day(d: date) -> float:
    """Julian day at 0h UT for the given Gregorian date."""
    y, m, day = d.year, d.month, d.day
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return math.floor(365.25 * (y + 4716)) + math.floor(30.6001 * (m + 1)) + day + b - 1524.5


def _solar_params(jd: float) -> tuple[float, float, float]:
    """Return (declination_deg, equation_of_time_min, true_longitude_deg)."""
    n = jd - 2451545.0
    g = math.radians((357.5291 + 0.98560028 * n) % 360.0)
    q = (280.4665 + 0.98564736 * n) % 360.0
    lam = math.radians((q + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)) % 360.0)
    eps = math.radians(23.439 - 0.0000004 * n)
    decl = math.degrees(math.asin(math.sin(eps) * math.sin(lam)))
    # equation of time (minutes)
    y = math.tan(eps / 2) ** 2
    eot = 4 * math.degrees(
        y * math.sin(2 * math.radians(q))
        - 2 * 0.0167 * math.sin(g)
        + 4 * 0.0167 * y * math.sin(g) * math.cos(2 * math.radians(q))
        - 0.5 * y * y * math.sin(4 * math.radians(q))
        - 1.25 * 0.0167**2 * math.sin(2 * g)
    )
    return decl, eot, math.degrees(lam)


def _hour_angle(lat: float, decl: float, alt: float) -> float | None:
    """Return the hour angle in hours from solar noon at which the sun reaches
    the given altitude. Returns None for circumpolar (no event)."""
    cos_h = (
        math.sin(math.radians(alt)) - math.sin(math.radians(lat)) * math.sin(math.radians(decl))
    ) / (math.cos(math.radians(lat)) * math.cos(math.radians(decl)))
    if cos_h >= 1.0 or cos_h <= -1.0:
        return None
    return math.degrees(math.acos(cos_h)) / 15.0  # hours


def _event_utc(d: date, lat: float, lon: float, alt: float, rising: bool) -> datetime | None:
    """UTC moment when the sun reaches `alt` for date `d` at lat/lon.

    `rising=True` returns the morning crossing; False returns the evening one.
    """
    jd = _julian_day(d)
    decl, eot, _ = _solar_params(jd + 0.5)  # noon midpoint
    h = _hour_angle(lat, decl, alt)
    if h is None:
        return None
    solar_noon_utc_hours = 12.0 - lon / 15.0 - eot / 60.0
    hours = solar_noon_utc_hours + (-h if rising else h)
    midnight = datetime(d.year, d.month, d.day, tzinfo=UTC)
    return midnight + timedelta(hours=hours)


def _fmt_local(dt: datetime | None, tz: ZoneInfo) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(tz).strftime("%H:%M")


def _resolve_tz(tz_name: str | None, lon: float) -> ZoneInfo:
    """Use named timezone if given; else round longitude to a fixed offset."""
    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            pass
    # Fallback: 15° per hour. round to nearest whole hour.
    offset_hours = round(lon / 15.0)
    return ZoneInfo(f"Etc/GMT{-offset_hours:+d}") if offset_hours else ZoneInfo("Etc/UTC")


# Default timezone hints for the cities exposed in the frontend dropdown.
_TZ_BY_HINT = {
    "Hobart": "Australia/Hobart",
    "Melbourne": "Australia/Melbourne",
    "Adelaide": "Australia/Adelaide",
    "Sydney": "Australia/Sydney",
    "Brisbane": "Australia/Brisbane",
    "Perth": "Australia/Perth",
    "Dunedin": "Pacific/Auckland",
    "Wellington": "Pacific/Auckland",
    "Auckland": "Pacific/Auckland",
}


def guess_timezone(label: str | None, lon: float) -> str:
    if label:
        for hint, tz in _TZ_BY_HINT.items():
            if hint.lower() in label.lower():
                return tz
    # longitude fallback
    offset_hours = round(lon / 15.0)
    return f"Etc/GMT{-offset_hours:+d}" if offset_hours else "Etc/UTC"


def local_night(
    lat: float,
    lon: float,
    *,
    request_utc: datetime,
    tz_name: str | None = None,
    location_label: str | None = None,
) -> NightWindow:
    """Compute the upcoming-night window for a location.

    "Upcoming night" = the night that *starts* on the local date of
    `request_utc`. If the request lands during local night already, we
    still return that night's bookends (so the briefing covers the
    rest-of-night). If it lands after sunrise, we return the *next*
    night.
    """
    tz_name = tz_name or guess_timezone(location_label, lon)
    tz = ZoneInfo(tz_name)
    local_now = request_utc.astimezone(tz)
    target_date = local_now.date()
    # If we're past sunrise local, target tonight (same date). If we're past
    # local midnight but before sunrise, the "current" night started on the
    # previous date — use that for sunset, today for sunrise.
    sunset = _event_utc(target_date, lat, lon, _SUN_ALT["sunset"], rising=False)
    sunrise_next = _event_utc(
        target_date + timedelta(days=1), lat, lon, _SUN_ALT["sunset"], rising=True
    )
    civil_dusk = _event_utc(target_date, lat, lon, _SUN_ALT["civil"], rising=False)
    civil_dawn = _event_utc(
        target_date + timedelta(days=1), lat, lon, _SUN_ALT["civil"], rising=True
    )
    astro_start = _event_utc(target_date, lat, lon, _SUN_ALT["astro"], rising=False)
    astro_end = _event_utc(
        target_date + timedelta(days=1), lat, lon, _SUN_ALT["astro"], rising=True
    )

    if sunset is None or sunrise_next is None:
        # polar night / midnight sun — fabricate sensible defaults
        sunset = datetime(target_date.year, target_date.month, target_date.day, 18, 0, tzinfo=UTC)
        sunrise_next = sunset + timedelta(hours=12)

    is_daylight = (
        civil_dusk is not None
        and civil_dawn is not None
        and (
            request_utc < civil_dusk - timedelta(minutes=5)
            or request_utc > civil_dawn + timedelta(minutes=5)
        )
        and not (civil_dusk <= request_utc <= civil_dawn)
    )

    return NightWindow(
        sunset_local=_fmt_local(sunset, tz) or "",
        civil_dusk_local=_fmt_local(civil_dusk, tz),
        astro_night_start_local=_fmt_local(astro_start, tz),
        astro_night_end_local=_fmt_local(astro_end, tz),
        civil_dawn_local=_fmt_local(civil_dawn, tz),
        sunrise_local=_fmt_local(sunrise_next, tz) or "",
        sunset_utc=sunset,
        sunrise_utc=sunrise_next,
        timezone=tz_name,
        is_daylight_now=is_daylight,
    )
