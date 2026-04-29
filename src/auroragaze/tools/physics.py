"""Auroral visibility from Kp.

The numbers below are the most equatorward geographic latitude at which
horizon glow has been reliably reported in the Australian sector,
calibrated against Bureau of Meteorology and `auroraaustralis.org.au`
event archives. Hobart (~43°S) reports aurora at Kp 5+, Melbourne (~38°S)
at Kp 6+, Brisbane (~27°S) at Kp 8+. v0.2 swaps in Ovation Prime.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from auroragaze.schemas import KpBin, NightWindow, Visibility, VisibilityWindow

# kp -> equatorward visibility threshold (degrees, geographic, southern hemisphere)
_VISIBILITY_THRESHOLD_LAT = {
    0: 65.0,
    1: 62.0,
    2: 58.0,
    3: 54.0,
    4: 50.0,
    5: 46.0,
    6: 42.0,
    7: 38.0,
    8: 34.0,
    9: 30.0,
}


def _threshold(kp: float) -> float:
    kp_floor = max(0, min(9, int(kp)))
    kp_ceil = max(0, min(9, int(kp) + 1))
    frac = max(0.0, min(1.0, kp - kp_floor))
    return (
        _VISIBILITY_THRESHOLD_LAT[kp_floor] * (1 - frac) + _VISIBILITY_THRESHOLD_LAT[kp_ceil] * frac
    )


def assess_visibility(lat: float, lon: float, kp: float) -> Visibility:
    threshold = _threshold(kp)
    abs_lat = abs(lat)
    margin = abs_lat - threshold
    if margin >= 0.0:
        level = "likely"
    elif margin >= -5.0:
        level = "possible"
    else:
        level = "unlikely"
    reasoning = (
        f"At Kp {kp:.1f} aurora glow is reliably reported as far equatorward as "
        f"~{threshold:.1f}°S in the Australian sector. The viewing latitude is "
        f"{abs_lat:.1f}°S; margin = {margin:+.1f}°."
    )
    return Visibility(
        level=level,
        boundary_lat_deg=round(threshold, 1),
        reasoning=reasoning,
    )


def _peak_kp_in_range(bins: list[KpBin], start: datetime, end: datetime) -> tuple[float, datetime]:
    """Return (max Kp, midpoint of the bin where it peaked) over a window.

    Bins overlap the window if they intersect at all. Empty intersection
    falls back to the first bin so we never return zero by accident.
    """
    relevant = [b for b in bins if b.end >= start and b.start <= end]
    if not relevant:
        relevant = bins[:1] or [KpBin(start=start, end=end, kp=0.0)]
    peak = max(relevant, key=lambda b: b.kp)
    midpoint = peak.start + (peak.end - peak.start) / 2
    return peak.kp, midpoint


def visibility_for_window(
    *,
    lat: float,
    lon: float,
    night: NightWindow,
    bins: list[KpBin],
) -> VisibilityWindow:
    """Compose forecast Kp + night window into per-sub-window visibility.

    Three sub-windows: evening (sunset→astro start), night (astro start→
    astro end, the prime block), dawn (astro end→sunrise). Visibility for
    each is the call against that sub-window's peak Kp.
    """
    # Anchor every sub-window in UTC for the bin overlap math.
    sset = night.sunset_utc
    sris = night.sunrise_utc

    # Astronomical-night bookends, falling back to civil twilight then sunset/sunrise.
    tz = ZoneInfo(night.timezone)
    base_date_local = sset.astimezone(tz).date()

    def _to_utc(local_str: str | None, fallback: datetime, next_day: bool) -> datetime:
        if not local_str:
            return fallback
        hh, mm = (int(x) for x in local_str.split(":"))
        d = base_date_local + (timedelta(days=1) if next_day else timedelta())
        local_dt = datetime(d.year, d.month, d.day, hh, mm, tzinfo=tz)
        return local_dt.astimezone(sset.tzinfo or fallback.tzinfo)

    astro_start = _to_utc(night.astro_night_start_local, sset, next_day=False)
    astro_end = _to_utc(night.astro_night_end_local, sris, next_day=True)
    if astro_start >= astro_end:
        # Skipped at high latitudes when no astronomical darkness occurs;
        # collapse to the full sunset→sunrise window.
        astro_start, astro_end = sset, sris

    evening_start = sset
    evening_end = astro_start
    night_start = astro_start
    night_end = astro_end
    dawn_start = astro_end
    dawn_end = sris

    eve_kp, eve_at = _peak_kp_in_range(bins, evening_start, evening_end)
    night_kp, night_at = _peak_kp_in_range(bins, night_start, night_end)
    dawn_kp, dawn_at = _peak_kp_in_range(bins, dawn_start, dawn_end)

    eve = assess_visibility(lat=lat, lon=lon, kp=eve_kp)
    nght = assess_visibility(lat=lat, lon=lon, kp=night_kp)
    dwn = assess_visibility(lat=lat, lon=lon, kp=dawn_kp)

    # Headline = the prime astronomical-night block. Peak time is the
    # local-time of the maximum Kp across the whole window.
    overall_peak_kp, overall_peak_at = max(
        ((eve_kp, eve_at), (night_kp, night_at), (dawn_kp, dawn_at)),
        key=lambda p: p[0],
    )

    summary_window = (
        f"{night.astro_night_start_local or night.civil_dusk_local or night.sunset_local} "
        f"→ {night.astro_night_end_local or night.civil_dawn_local or night.sunrise_local} "
        f"({night.timezone.split('/')[-1]})"
    )

    return VisibilityWindow(
        evening=eve,
        night=nght,
        dawn=dwn,
        peak_local=overall_peak_at.astimezone(tz).strftime("%H:%M"),
        peak_kp=round(overall_peak_kp, 2),
        headline_level=nght.level,
        summary_window=summary_window,
    )
