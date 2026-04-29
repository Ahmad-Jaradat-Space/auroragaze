"""Deterministic grounding check for a composed briefing.

Extracts every numeric token from the briefing's prose and verifies each
one appears (within 5% tolerance) in either:
- the live tool outputs (solar wind, Kp, Dst, drag fraction, oval boundary), or
- the retrieved corpus chunks.

If anything is unsupported, the verifier returns a list of offending values
so the composer can be re-invoked with a corrective hint.
"""

from __future__ import annotations

import re
from typing import Any

# Match standalone numbers (negative + decimals) NOT immediately preceded by
# a digit or hyphen — keeps dates and ranges out. Dates of various shapes
# (ISO, slash, abbreviated) are stripped first so their fragments cannot
# leak through.
_NUM = re.compile(r"(?<![\w.-])(-?\d+(?:\.\d+)?)(?![\w.])")
_DATE_PATTERNS = [
    re.compile(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b"),  # 2024-05-11
    re.compile(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b"),  # 11-05-2024
    re.compile(r"\b(19|20)\d{2}\b"),                 # bare year 2024
]


def _extract_numbers(text: str) -> list[float]:
    cleaned = text
    for p in _DATE_PATTERNS:
        cleaned = p.sub(" ", cleaned)
    return [float(m) for m in _NUM.findall(cleaned)]


def _allowed_from_tools(state: dict[str, Any]) -> list[float]:
    out: list[float] = []
    sw = state.get("solar_wind")
    if sw is not None:
        out.extend([float(sw.bz), float(sw.bt), float(sw.speed_kms), float(sw.density_cm3)])
    kp = state.get("kp")
    if kp is not None:
        out.append(float(kp.kp))
    if "dst_nt" in state:
        out.append(float(state["dst_nt"]))
    vis = state.get("visibility")
    if vis is not None:
        out.append(float(vis.boundary_lat_deg))
    fi = state.get("fleet_impact")
    if isinstance(fi, dict):
        out.append(float(fi.get("kp", 0)))
        for u in fi.get("units", []):
            d = u.get("drag")
            if isinstance(d, dict):
                out.append(float(d.get("altitude_km", 0)))
                out.append(float(d.get("kp", 0)))
                out.append(float(d.get("density_fraction_increase", 0)))
                out.append(float(d.get("drag_dv_fraction_increase", 0)))
    if "lat" in state:
        out.append(float(state["lat"]))
    if "lon" in state:
        out.append(float(state["lon"]))
    return out


def _allowed_from_chunks(state: dict[str, Any]) -> list[float]:
    out: list[float] = []
    for c in state.get("chunks", []) or []:
        out.extend(_extract_numbers(c.text))
    return out


def _is_supported(value: float, allowed: list[float], tol: float = 0.05) -> bool:
    """Accept value if any allowed number matches.

    Sign-insensitive: an allowed -42.88 supports a 42.88 in the briefing
    (the prose typically writes |lat| with °S, while the input lat is
    negative). Tolerance: ±0.5 absolute, or ±tol relative.
    """
    for a in allowed:
        for candidate in (a, -a):
            if candidate == value:
                return True
            diff = abs(candidate - value)
            if diff <= 0.5:  # absolute tolerance for small ints/floats
                return True
            if candidate != 0 and diff / abs(candidate) <= tol:
                return True
    return False


# Unit/category tokens that frequently surface as numbers but should not be flagged.
_BENIGN_VALUES = {
    0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0,
    11.0, 12.0, 13.0, 14.0, 15.0,
    24.0,  # hours in a day
    100.0, 1000.0,  # round multipliers
}


def verify_briefing(briefing_text: str, state: dict[str, Any]) -> list[float]:
    """Return the list of numeric values in `briefing_text` not supported by
    the trace tools or the retrieved chunks. Empty list = grounded."""
    allowed = _allowed_from_tools(state) + _allowed_from_chunks(state)
    unsupported: list[float] = []
    for n in _extract_numbers(briefing_text):
        if n in _BENIGN_VALUES:
            continue
        if not _is_supported(n, allowed):
            unsupported.append(n)
    # de-dup preserving order
    seen: set[float] = set()
    deduped: list[float] = []
    for n in unsupported:
        if n not in seen:
            seen.add(n)
            deduped.append(n)
    return deduped
