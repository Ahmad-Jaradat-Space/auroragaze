"""Atmospheric drag delta during a geomagnetic storm.

Uses NOAA SWPC empirical density-increase estimates by altitude and storm
strength (G-scale). Returns a drag delta-v fraction relative to nominal
station-keeping cadence. Numbers are calibration-quality, not flight-grade;
the citation in the corpus (`ref-drag-table.txt`) is the authoritative
source for downstream briefings.
"""

from pydantic import BaseModel

# (altitude_floor_km, kp_floor): density increase fraction (additive over 1.0)
_TABLE = {
    300: {0: 0.0, 5: 0.25, 6: 0.45, 7: 0.65, 8: 1.5, 9: 3.0},
    500: {0: 0.0, 5: 0.075, 6: 0.15, 7: 0.225, 8: 0.5, 9: 1.05},
    800: {0: 0.0, 5: 0.035, 6: 0.07, 7: 0.115, 8: 0.2, 9: 0.425},
}


def _interp_kp(curve: dict[int, float], kp: float) -> float:
    keys = sorted(curve.keys())
    kp_clamped = max(keys[0], min(keys[-1], kp))
    lower = max(k for k in keys if k <= kp_clamped)
    upper = min(k for k in keys if k >= kp_clamped)
    if lower == upper:
        return curve[lower]
    frac = (kp_clamped - lower) / (upper - lower)
    return curve[lower] * (1 - frac) + curve[upper] * frac


def _interp_alt(altitude_km: float, kp: float) -> float:
    keys = sorted(_TABLE.keys())
    a = max(keys[0], min(keys[-1], altitude_km))
    lower = max(k for k in keys if k <= a)
    upper = min(k for k in keys if k >= a)
    if lower == upper:
        return _interp_kp(_TABLE[lower], kp)
    frac = (a - lower) / (upper - lower)
    return _interp_kp(_TABLE[lower], kp) * (1 - frac) + _interp_kp(_TABLE[upper], kp) * frac


class DragDelta(BaseModel):
    altitude_km: float
    kp: float
    density_fraction_increase: float
    drag_dv_fraction_increase: float
    severity: str
    table_source: str = "NOAA SWPC empirical density estimates; JB2008 ranges"


def compute_drag_delta(altitude_km: float, kp: float) -> DragDelta:
    density_frac = _interp_alt(altitude_km, kp)
    # drag delta-v scales linearly with density at fixed velocity and ballistic coefficient
    dv_frac = density_frac
    if dv_frac < 0.10:
        sev = "low"
    elif dv_frac < 0.50:
        sev = "moderate"
    elif dv_frac < 1.5:
        sev = "high"
    else:
        sev = "extreme"
    return DragDelta(
        altitude_km=altitude_km,
        kp=kp,
        density_fraction_increase=round(density_frac, 3),
        drag_dv_fraction_increase=round(dv_frac, 3),
        severity=sev,
    )
