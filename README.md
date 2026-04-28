# AuroraGaze

> Live solar-wind briefings for southern-hemisphere aurora chasers.

This repo is under construction. v0.1 ships when the live demo is up and the eval gate is green.

## What it does (target v0.1)

Reads real-time solar-wind data at L1 (NOAA DSCOVR), runs a five-node LangGraph
agent over a curated event corpus, and answers one question for southern-hemisphere
chasers: *can I see the aurora tonight, and from where?*

## Stack

DeepSeek V3, LangGraph, ChromaDB, sentence-transformers, FastAPI + SSE, MCP server,
single-page HTML frontend.

## Releases

| tag  | what | when |
|------|------|------|
| v0.1 | RAG + multi-agent + MCP + live demo | day 3 |
| v0.2 | satellite persona, reranker, red-team evals | later |
| v0.3 | hosted with cost discipline + Langfuse | later |
