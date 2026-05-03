# 0006 — Drive radius and ranked viewing spots

## Context

The original aurora briefing answered "can I see aurora *at city X* tonight?" Real
chasers don't think that way. From Hobart, the difference between a clouded-out
yes/no and a great night is often a 40 km drive south to South Arm or Tinderbox
where the sky is clear and the southern horizon is open. We needed a feature
that respects how chasers actually plan: a drive radius, and a ranked list of
named candidate spots inside it.

## Decision

Add a `radius_km` slider (5..300 km) and a `ranked_spots` array on the briefing.
A new graph node, `nearby_spots_node`, runs after the data fetcher and produces
the ranking. Three new tools and one ranker:

| Tool | Source | Why |
|---|---|---|
| `tools/spots.py` | OpenStreetMap **Overpass API** (free, no key) | Real-world named viewpoints, peaks, nature reserves. Falls back to a hex-grid sample if Overpass is down or yields <5 hits — the pipeline is never empty. |
| `tools/cloud.py` | **Open-Meteo** forecast API (free, no key) | Cloud-cover hourly forecast for tonight's window, batched in one HTTP call across all candidate coords. The factor most likely to flip a decision in coastal southern Australia. |
| `tools/light_pollution.py` | OSM `place=*` nodes with population, no raster | Distance-and-population heuristic. The plan called for the **Falchi 2016 World Atlas of Artificial Sky Brightness** GeoTIFF; we deferred it because (a) it needs `rasterio` (~50 MB binary deps, fragile to install on Fly.io's slim base), and (b) the heuristic is good enough to differentiate "central Hobart" from "Mt Wellington summit" from "Bruny Island". v2 can swap in Falchi without changing callers. |
| `tools/ranker.py` | composite score | Weights: `0.45 * geomag + 0.30 * (1 - cloud) + 0.15 * bortle - 0.10 * distance_penalty`. Geomagnetic latitude is the dominant physics factor; cloud cover is the dominant meteorology factor; darkness is a tiebreaker; distance is a soft penalty so a marginally-better spot 250 km away doesn't beat a nearly-as-good one 30 km away. |

The base location is always candidate #0, so chasers can see the trade-off of
staying put versus driving out. The score is `0..1`, the rank is sequential, and
each spot carries a one-sentence `why` blurb summarising what drove its placement
("Clearer skies (15% vs 90% cloud), much darker (Bortle 3 vs 7), ~32 km S").

## Consequences

- **Latency**: one extra Overpass round-trip + one Open-Meteo round-trip on the
  aurora persona. Both have generous free tiers; total added wall time ≈ 2–4 s
  for radius=80 km. Acceptable for a briefing that already runs 6–10 s.
- **Failure mode**: if Overpass is unreachable, we hex-grid; if Open-Meteo is
  unreachable, every candidate gets cloud=50 (neutral) and the ranker still works.
- **Verifier surface**: the verifier's "allowed numbers" pool grows by every
  ranked-spot distance, cloud %, Bortle, and lat/lon — so the LLM can quote spot
  details without tripping grounding. Already implemented.
- **MCP**: a 7th primitive, `nearby_viewing_spots(lat, lon, radius_km)`, exposes
  the same ranked list to Claude Desktop and any MCP client.
- **Frontend**: the single curated `gaze` pin per city becomes a multi-pin
  overlay scaled by score. `CITIES[idx].gaze` is no longer load-bearing — it
  remains in the array as a fallback hint but the backend supplies spots
  dynamically.
- **Ethics / privacy**: no user data leaves the box; OSM and Open-Meteo are
  queried with anonymous user-agent strings.

## Out of scope (revisit in v2)

- Live drive-time routing (OSRM / Google) — currently great-circle distance with
  a soft exponential penalty. Good enough to differentiate 30 km from 200 km.
- Southern-horizon openness from SRTM elevation tiles — meaningful for chasers
  in mountainous terrain. Adds a heavy data dependency; deferred.
- Falchi-grade Bortle from the published GeoTIFF — see above. The current OSM
  proxy is calibrated against published Bortle values for Hobart, Mt Wellington,
  and Bruny Island; v2 swap should match within ±1 class.
