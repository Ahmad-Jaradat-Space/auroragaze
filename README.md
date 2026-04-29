# AuroraGaze

> Live solar-wind briefings for southern-hemisphere aurora chasers and satellite operators. Real DSCOVR data, multi-agent reasoning, grounded citations.

[![ci](https://github.com/Ahmad-Jaradat-Space/auroragaze/actions/workflows/ci.yml/badge.svg)](https://github.com/Ahmad-Jaradat-Space/auroragaze/actions/workflows/ci.yml)

### → [Open the live demo](https://auroragaze.fly.dev)

![hero](docs/img/hero.png)

---

## Why it exists

Two communities watch the same upstream physics and need two completely different translations to action. Existing tools serve neither well.

### Aurora chasers in southern Australia and New Zealand

Tasmania, Victoria, southern South Australia, the South Island of NZ — there is a serious community that watches the southern auroral oval (90 000+ in the *Aurora Australis* Facebook group, the public archive at `auroraaustralis.org.au`, tourism operators around Hobart and Bruny Island). Existing tools give them either bare indices ("Kp is 7") or northern-hemisphere-centric forecasts. The translation gap is between the upstream measurement and the actual viewing decision: *should I drive to the dark-sky site tonight, what time, facing which way?*

![aurora briefing card](docs/img/aurora-card.png)

### Satellite operators

In February 2022 SpaceX deployed 49 Starlink satellites into a 210 km parking orbit. A small geomagnetic storm hit a day later. Thermospheric density at that altitude roughly doubled, atmospheric drag overwhelmed the satellites' ability to climb, and **38 of 49 re-entered**. The storm was small; the operational impact was severe. That event is the canonical case for *storm-time density forecasts existed but weren't translated into ops actions in time*. Operators today still see NOAA G-scales and read bulletins by hand.

![satellite briefing card](docs/img/satellite-card.png)

Same physics. Two translations to action. **One product.**

---

## What it is

AuroraGaze polls live solar-wind data at L1 (NOAA DSCOVR), runs it through a six-node multi-agent system, and produces grounded briefings with citations. Open the live demo, pick a city or a fleet, click *Get briefing*, and watch the agent trace stream live as it works.

![agent trace streaming](docs/img/agent-trace.png)

Live imagery from NASA SDO and NOAA SWPC sits above the data widgets so the system feels like an instrument, not a dashboard:

![live imagery strip](docs/img/imagery.png)

### → [Try it now](https://auroragaze.fly.dev)

---

## How it works

```
              ┌─────────────────┐
              │   supervisor    │  sets persona, query
              └─────────┬───────┘
                        │
        ┌───────────────┴───────────────┐
        ▼ (parallel)                    ▼ (parallel)
  ┌──────────────┐               ┌──────────────┐
  │ data_fetcher │               │  retrieval   │
  │ 4 NOAA tools │               │ dense+rerank │
  └──────┬───────┘               └──────┬───────┘
         │                              │
         └──────────────┬───────────────┘
                        ▼
                 ┌─────────────┐
                 │   physics   │  pure functions
                 │ vis OR fleet│  (oval, drag, fleet)
                 └─────┬───────┘
                       │
              ┌────────┴─────────┐
              ▼ persona=aurora   ▼ persona=satellite
       ┌─────────────────┐  ┌──────────────────────┐
       │ aurora_composer │  │ satellite_composer   │
       │   LLM call      │  │     LLM call         │
       └─────────────────┘  └──────────────────────┘
```

Six nodes, **one LLM call** per briefing. The intelligence lives in the retrieval and physics layers, not in token sampling. The composer's only job is to write a cited paragraph from typed state — it never invents a number. ADRs in [`docs/decisions/`](docs/decisions/) carry the full rationale.

### Stack

- **DeepSeek V3** (`deepseek-chat`) via `langchain-deepseek` — provider-agnostic factory, swap with one env var.
- **LangGraph** — six-node graph, parallel `data_fetcher` ‖ `retrieval`, conditional persona routing.
- **ChromaDB + bge-small-en-v1.5** dense retrieval, **bge-reranker-v2-m3** cross-encoder for top-5 precision.
- **FastAPI + SSE** streaming the agent trace; **single-page HTML + Tailwind CDN + Leaflet** frontend.
- **MCP server** (FastMCP) exposing six primitives to Claude Desktop and any MCP client.
- **Docker** multi-stage build, **Fly.io** Sydney region, auto-stop on idle.

---

## Eval

20-event golden set, 10 aurora and 10 satellite, hand-curated against NOAA SWPC archives and `auroraaustralis.org.au` reports. Latest run on `main`:

| | cited | grounded | correct |
|---|---|---|---|
| aurora (n=10) | 1.00 | 0.70 | **1.00** |
| satellite (n=10) | 1.00 | 0.80 | 0.70 |
| **overall** | **1.00** | **0.75** | **0.85** |

**Overall precision 0.867** — CI gate at 0.80, calibration in [`eval/calibration.md`](eval/calibration.md).

The judge is hybrid: deterministic checks for `cited` and `correct`, LLM judge for `grounded`. Both must agree where deterministic checks apply. Reproduce locally:

```
python eval/run_eval.py --out eval/results.json
python eval/judge.py --in eval/results.json --out eval/results_judged.json
```

---

## MCP

Six tools available to any MCP client. To install in Claude Desktop, add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

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

Tools: `get_solar_wind`, `get_kp_now`, `get_dst_now`, `assess_visibility`, `compute_drag_delta_tool`, `retrieve_context`.

---

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

The image bakes in the embedding model and an ingested ChromaDB so the container boots ready-to-serve. See [`deploy/hetzner.md`](deploy/hetzner.md) for the alternative single-VPS path.

---

## Architecture decisions

The five load-bearing choices, each as its own ADR:

1. [DeepSeek over Anthropic](docs/decisions/0001-llm-provider.md) — cost discipline and provider lock-in.
2. [Hard-coded six-node graph, not ReAct](docs/decisions/0002-graph-shape.md) — deterministic pipeline, debuggable, predictable cost.
3. [ChromaDB + BGE + reranker](docs/decisions/0003-rag-stack.md) — self-contained retrieval, swappable.
4. [MCP exposes primitives, not the briefing](docs/decisions/0004-mcp-scope.md) — tools compose; black-box endpoints don't.
5. [Physics is plain Python, not an LLM call](docs/decisions/0005-physics-not-llm.md) — the most important: the engineer knows when *not* to use the LLM.

---

## Out of scope

- Forecasting. AuroraGaze monitors and translates; it does not forecast.
- Northern-hemisphere aurora.
- Vendor-specific safe-mode procedures.
- Authoritative regulatory advice. Briefings are decision-support.

---

## Why I built this

Geodesy and space-weather sit close to each other — both watch the same solar wind, both need it translated into action. The February 2022 Starlink loss is the case where storm-time density forecasts existed but weren't translated into ops actions in time. Australia has one of the world's most active southern-hemisphere aurora communities, but operational tools are northern-hemisphere-centric or bare indices. Same physics, two translations to action — one product.

Sources: NOAA SWPC, DSCOVR, GOES, Kyoto World Data Center, NASA SDO, `auroraaustralis.org.au`, Bureau of Meteorology Space Weather Services.
