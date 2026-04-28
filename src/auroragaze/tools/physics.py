"""Auroral visibility from Kp.

The numbers below are the most equatorward geographic latitude at which
horizon glow has been reliably reported in the Australian sector,
calibrated against Bureau of Meteorology and `auroraaustralis.org.au`
event archives. Hobart (~43°S) reports aurora at Kp 5+, Melbourne (~38°S)
at Kp 6+, Brisbane (~27°S) at Kp 8+. v0.2 swaps in Ovation Prime.
"""

from auroragaze.schemas import Visibility

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
