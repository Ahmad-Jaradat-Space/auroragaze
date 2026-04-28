# 0002 — Hard-coded six-node graph, not a single ReAct agent

## Context

The briefing pipeline has known stages: fetch live data, retrieve relevant
analogues, compute a physics quantity, compose the briefing. The same
ordering applies for both personas (aurora chaser, satellite operator).

The alternative is a single ReAct agent with all the tools attached and the
LLM iteratively choosing what to call.

## Decision

Six-node `StateGraph`: supervisor → (data_fetcher ‖ retrieval) → physics →
{aurora_composer | satellite_composer}. Only the composer makes an LLM call.
All other "intelligence" (data fetching, retrieval, physics) is plain
Python with typed I/O.

Parallel `data_fetcher` and `retrieval` write to a `trace` channel
annotated with `operator.add` so concurrent writes accumulate.

## Consequences

- One LLM call per briefing instead of five to ten ReAct iterations. Cost
  goes down by an order of magnitude; latency by a similar factor.
- Deterministic eval. The same query produces the same tool sequence every
  time; only the composer output varies. The eval judge can compare like
  with like.
- Debuggable: each node has one job and one failure surface. A bug in
  retrieval cannot manifest as a hallucinated index.
- The graph's topology becomes the agent trace the user sees in the UI.
  This is what makes the multi-agent system *visible*, not just a
  backend detail.
- ReAct still earns its keep where exploration is the point — a planned
  follow-up adds a ReAct sub-agent inside the retrieval node for analogue
  searches with iteratively refined criteria, called as a tool by the
  retrieval node when the supervisor flags `need_analogue=True`.
- The trade is reduced flexibility for predictable behaviour. For a
  deterministic monitoring product this is the right call; for an
  open-ended research assistant it would be the wrong one.
