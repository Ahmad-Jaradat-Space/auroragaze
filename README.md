# AuroraGaze

> Live solar-wind briefings for southern-hemisphere aurora chasers and satellite operators.

[![ci](https://github.com/Ahmad-Jaradat-Space/auroragaze/actions/workflows/ci.yml/badge.svg)](https://github.com/Ahmad-Jaradat-Space/auroragaze/actions/workflows/ci.yml)

**Live demo:** https://auroragaze.fly.dev

AuroraGaze reads real-time solar-wind data at L1 (NOAA DSCOVR) and
translates it into two kinds of briefing:

- **Aurora chasers in southern Australia and New Zealand** — where, when,
  how bright, facing where.
- **Satellite operators** — fleet-level impact and recommended actions,
  anchored on the February 2022 Starlink loss as the reference case.

Same upstream physics; different translations to action.

## How it works

A six-node LangGraph runs every briefing:

```
supervisor -> data_fetcher  ┐
          \                 ├─> physics -> composer -> END
           -> retrieval     ┘
```

- `data_fetcher` calls four NOAA SWPC tools (DSCOVR solar wind, planetary
  Kp, Kyoto Dst, GOES X-ray) in parallel with `retrieval`.
- `retrieval` runs hybrid RAG: dense top-20 with `bge-small-en-v1.5`
  through ChromaDB, then reranked top-5 with `bge-reranker-v2-m3`.
- `physics` calls a typed function — `assess_visibility(lat, lon, kp)`
  for aurora, `assess_fleet_impact(fleet, kp)` for satellite — and writes
  the typed result back to state.
- `composer` is the only LLM call. DeepSeek V3 with structured output
  produces an `AuroraBriefing` or `SatelliteBriefing`. Numbers come from
  tool outputs and corpus chunks; the composer never invents.

The streamed agent trace is the UI. Every step appears as it happens.

## Stack

- DeepSeek V3 via `langchain-deepseek` (Anthropic-free; provider-swappable)
- LangGraph, FastAPI + Server-Sent Events
- ChromaDB local-persistent + sentence-transformers BGE
- MCP server (FastMCP) exposing six tools
- Pydantic models on every I/O boundary
- Vanilla HTML + Tailwind CDN frontend; soft-pastel iOS-inspired
- Fly.io with a single Dockerfile

## Eval

20-event golden set, 10 aurora and 10 satellite, hand-curated against
NOAA SWPC archives and `auroraaustralis.org.au` reports. Each briefing
is scored on three booleans: `cited`, `grounded` (no fabricated numbers),
`correct` (matches expected outcome). Calibration in
[`eval/calibration.md`](eval/calibration.md).

Latest run on `main` (DeepSeek V3, 20 events):

| | cited | grounded | correct | overall |
|---|---|---|---|---|
| aurora (n=10) | 1.00 | 0.70 | 1.00 | |
| satellite (n=10) | 1.00 | 0.80 | 0.70 | |
| **overall** | **1.00** | **0.75** | **0.85** | **0.867** |

CI eval gate fails below 0.80 overall precision. Run locally:

```
python eval/run_eval.py --out eval/results.json
python eval/judge.py --in eval/results.json --out eval/results_judged.json
```

## MCP

The MCP server makes AuroraGaze's primitives available to any MCP client.
Six tools: `get_solar_wind`, `get_kp_now`, `get_dst_now`,
`assess_visibility`, `compute_drag_delta_tool`, `retrieve_context`.

To install in Claude Desktop, add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "auroragaze": {
      "command": "/path/to/auroragaze/.venv/bin/python",
      "args": ["-m", "auroragaze.mcp_server.server"],
      "env": { "DEEPSEEK_API_KEY": "sk-..." }
    }
  }
}
```

## Run locally

```
git clone https://github.com/Ahmad-Jaradat-Space/auroragaze
cd auroragaze
uv venv --python 3.11 .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
cp .env.example .env  # fill DEEPSEEK_API_KEY
python -c "from auroragaze.retrieval.ingest import ingest_corpus; ingest_corpus()"
uvicorn auroragaze.api.main:app --reload
# open http://localhost:8000
```

CLI:

```
python -m auroragaze brief --lat -42.88 --lon 147.32 --location Hobart
python -m auroragaze fleet-brief --fleet examples/fleet.json --label "LEO constellation"
```

## Deploy

```
fly launch --copy-config --no-deploy
fly secrets set DEEPSEEK_API_KEY=sk-...
fly deploy
```

The image bakes in the embedding model, reranker, and an ingested
ChromaDB so the container boots ready-to-serve. See
[`deploy/hetzner.md`](deploy/hetzner.md) for the alternative
single-VPS path.

## Architecture decisions

The five load-bearing choices live in [`docs/decisions/`](docs/decisions/):

1. [DeepSeek over Anthropic](docs/decisions/0001-llm-provider.md) — cost and provider lock-in.
2. [Hard-coded six-node graph, not ReAct](docs/decisions/0002-graph-shape.md) — deterministic pipeline, debuggable, predictable cost.
3. [ChromaDB + BGE + reranker](docs/decisions/0003-rag-stack.md) — self-contained, swappable.
4. [MCP exposes primitives, not the briefing](docs/decisions/0004-mcp-scope.md) — tools compose; black-box endpoints don't.
5. [Physics is plain Python, not an LLM call](docs/decisions/0005-physics-not-llm.md) — most important: the engineer knows when not to use the LLM.

## Out of scope

- Forecasting. AuroraGaze monitors and translates; it does not forecast.
- Northern-hemisphere aurora.
- Vendor-specific safe-mode procedures.
- Authoritative regulatory advice. Briefings are decision-support.

## Why I built this

Geodesy and space-weather sit close to each other — both watch the same
solar wind, both need it translated into action. The February 2022
Starlink loss is the case where storm-time density forecasts existed but
weren't translated into ops actions in time. Australia has one of the
world's most active southern-hemisphere aurora communities (`auroraaustralis.org.au`,
the *Aurora Australis* Facebook group), but operational tools are
northern-hemisphere-centric or bare indices. Same physics, two
translations to action — one product.

Sources: NOAA SWPC, DSCOVR, GOES, Kyoto World Data Center,
`auroraaustralis.org.au`, Bureau of Meteorology Space Weather Services.
