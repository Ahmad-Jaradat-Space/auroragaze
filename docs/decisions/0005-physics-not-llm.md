# 0005 — Physics is plain Python, not an LLM call

## Context

Auroral oval extent and atmospheric drag are well-defined functions of
geomagnetic activity, with tables published by NOAA SWPC and used by
operational forecasters. The composer LLM could in principle produce these
estimates from the corpus, but with a non-zero rate of fabrication.

## Decision

Two pure functions, both unit-tested:
- `assess_visibility(lat, lon, kp) -> Visibility` uses an interpolation
  table calibrated against published southern-hemisphere viewing thresholds.
- `compute_drag_delta(altitude_km, kp) -> DragDelta` uses NOAA SWPC
  empirical density-increase ranges by altitude and Kp.

The composer receives the typed result and quotes it. The composer never
estimates these numbers itself.

## Consequences

- Numbers in the briefing come from a tool, not from the LLM. The eval
  judge can deterministically check this by inspecting the citations.
- The functions are calibration-quality, not flight-grade. The doctring on
  each function names the published source and the limitation. The
  briefing language reflects the same caveat ("calibration-quality
  estimate, not a flight planning input").
- Upgrading either function (e.g. swapping in Ovation Prime for the
  visibility model) is a file change with no ripple into the graph. The
  composer prompt does not need to know the model changed.
- This is the single most important design choice for hiring-manager
  legibility: it shows the engineer knows when *not* to use the LLM.
