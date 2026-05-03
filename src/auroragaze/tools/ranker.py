"""Composite ranker for candidate viewing spots.

Score blends four factors, each normalised to 0..1 (higher = better):

    score = W_GEOMAG  * geomag_score       # latitude vs Kp boundary
          + W_CLOUD   * (1 - cloud/100)    # clearer sky → higher
          + W_BORTLE  * bortle_score       # darker sky → higher
          - W_DIST    * distance_penalty   # further drive → lower

Weights are deliberately heavy on geomagnetic latitude (the physics of
"will aurora reach this latitude") and cloud cover (the meteorology of
"can I see it"), with darkness as a tiebreaker and distance a soft
penalty so a marginally better spot 200 km away doesn't beat a nearly
as good one 30 km away.

Each ranked spot also carries a one-sentence `why` explaining what
drove its rank, so the briefing card can render a human rationale.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from auroragaze.schemas import KpBin, NightWindow, RankedSpot, Visibility
from auroragaze.tools.light_pollution import bortle_score
from auroragaze.tools.physics import visibility_for_window
from auroragaze.tools.spots import Candidate

# Weights (sum to 1.0 for the positive components; distance is a separate penalty).
W_GEOMAG = 0.45
W_CLOUD = 0.30
W_BORTLE = 0.15
W_DIST = 0.10  # subtracted

DIST_HALF_KM = 80.0  # 50 % penalty at this distance


def _geomag_score(visibility: Visibility, viewer_abs_lat: float) -> float:
    """Map margin (viewer_lat - oval_threshold) to a 0..1 score.

    margin >=  0  → 1.0   (likely)
    margin == -5  → 0.5   (possible boundary)
    margin <= -10 → 0.0   (well out of reach)
    """
    margin = viewer_abs_lat - visibility.boundary_lat_deg
    return max(0.0, min(1.0, 0.5 + margin / 10.0))


def _distance_penalty(distance_km: float) -> float:
    """Soft 0..1 penalty: 0 at base, ~0.5 at DIST_HALF_KM, ~1 at 5x that."""
    return 1.0 - math.exp(-distance_km / DIST_HALF_KM)


@dataclass
class _Scored:
    candidate: Candidate
    visibility: Visibility
    cloud_pct: int
    bortle: int
    score: float
    geomag: float
    distance_km: float


def _why(scored: _Scored, base: _Scored) -> str:
    """One sentence explaining why this spot ranks where it does."""
    c = scored.candidate
    if c.is_base:
        return "Your base location — the trade-off baseline for the spots below."
    parts: list[str] = []
    cloud_delta = base.cloud_pct - scored.cloud_pct
    if cloud_delta >= 15:
        parts.append(f"clearer skies ({scored.cloud_pct}% vs {base.cloud_pct}% cloud)")
    elif cloud_delta <= -15:
        parts.append(f"cloudier ({scored.cloud_pct}% vs {base.cloud_pct}%)")
    bortle_delta = base.bortle - scored.bortle
    if bortle_delta >= 2:
        parts.append(f"much darker (Bortle {scored.bortle} vs {base.bortle})")
    elif bortle_delta == 1:
        parts.append(f"slightly darker (Bortle {scored.bortle} vs {base.bortle})")
    geomag_delta = scored.geomag - base.geomag
    if geomag_delta >= 0.05:
        parts.append("a touch closer to the auroral oval")
    if not parts:
        parts.append("similar conditions to base")
    parts.append(f"~{round(scored.distance_km)} km {c.bearing}")
    return ", ".join(parts).capitalize() + "."


def rank_spots(
    *,
    base_lat: float,
    candidates: list[Candidate],
    night: NightWindow,
    bins: list[KpBin],
    cloud_lookup: dict[tuple[float, float], int],
    bortle_lookup: dict[tuple[float, float], int],
) -> list[RankedSpot]:
    """Score and rank every candidate; return them best-first.

    `cloud_lookup` and `bortle_lookup` are keyed by (round(lat,3), round(lon,3))
    matching the helpers in `tools.cloud` and the light-pollution module.
    Missing entries default to 50 % cloud and Bortle 5 (neutral).
    """
    if not candidates:
        return []

    scored: list[_Scored] = []
    for c in candidates:
        # Per-spot geomag visibility: re-run window math for that lat.
        vw = visibility_for_window(lat=c.lat, lon=c.lon, night=night, bins=bins)
        v = vw.night
        geomag = _geomag_score(v, abs(c.lat))
        cloud = cloud_lookup.get((round(c.lat, 3), round(c.lon, 3)), 50)
        bortle = bortle_lookup.get((round(c.lat, 3), round(c.lon, 3)), 5)
        cloud_term = 1.0 - cloud / 100.0
        bortle_term = bortle_score(bortle)
        dist_pen = _distance_penalty(c.distance_km)
        s = (
            W_GEOMAG * geomag
            + W_CLOUD * cloud_term
            + W_BORTLE * bortle_term
            - W_DIST * dist_pen
        )
        s = max(0.0, min(1.0, s))
        scored.append(
            _Scored(
                candidate=c,
                visibility=v,
                cloud_pct=cloud,
                bortle=bortle,
                score=s,
                geomag=geomag,
                distance_km=c.distance_km,
            )
        )

    base = next((s for s in scored if s.candidate.is_base), scored[0])
    # Sort: base preserved separately, others by score desc.
    others = [s for s in scored if not s.candidate.is_base]
    others.sort(key=lambda s: (-s.score, s.distance_km))
    final = [base] + others

    out: list[RankedSpot] = []
    for rank, s in enumerate(final, start=1):
        out.append(
            RankedSpot(
                name=s.candidate.name,
                lat=round(s.candidate.lat, 4),
                lon=round(s.candidate.lon, 4),
                distance_km=round(s.candidate.distance_km, 1),
                bearing=s.candidate.bearing,
                geomag_visibility=s.visibility,
                cloud_pct=s.cloud_pct,
                bortle=s.bortle,
                score=round(s.score, 3),
                rank=rank,
                why=_why(s, base),
                is_base=s.candidate.is_base,
            )
        )

    # Re-sort the final output so rank 1 is the truly best spot
    # (which may be the base, may be a remote site).
    out.sort(key=lambda r: (-r.score, r.distance_km))
    for i, rs in enumerate(out, start=1):
        rs_rank_fixed = rs.model_copy(update={"rank": i})
        out[i - 1] = rs_rank_fixed

    return out
