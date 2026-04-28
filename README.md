# AuroraGaze

> Live solar-wind briefings for southern-hemisphere aurora chasers and satellite operators.

Reads real-time solar-wind data at L1 (NOAA DSCOVR) and translates it into two
kinds of briefing:

- **Aurora chasers in southern Australia and NZ** — where, when, how bright, facing where.
- **Satellite operators** — fleet-level impact and recommended actions, anchored
  on the February 2022 Starlink loss as the canonical case.

This README is provisional while the product is being built. The full version
lands when the live demo is up.

## How it works

A six-node LangGraph runs every briefing:

```
supervisor → data_fetcher ‖ retrieval → physics → composer
```

- `data_fetcher` calls NOAA SWPC data tools (solar wind, Kp, Dst, GOES X-ray).
- `retrieval` runs hybrid RAG (dense + reranker) over a curated event corpus
  and a ReAct sub-agent for analogue search.
- `physics` calls the right physics tool for the persona (auroral oval geometry
  or atmospheric drag).
- `composer` writes the cited briefing.

Every numeric value cites its source and timestamp. The agent calls a tool
or quotes a corpus chunk — it does not invent.

## Stack

DeepSeek V3, LangGraph, ChromaDB + `bge-small-en-v1.5`, `bge-reranker-v2-m3`,
FastAPI + SSE, MCP server, Langfuse, Fly.io.

## Out of scope

- Forecasting — AuroraGaze monitors and translates, it does not forecast.
- Northern-hemisphere aurora.
- Vendor-specific safe-mode procedures.
- Authoritative regulatory advice.
