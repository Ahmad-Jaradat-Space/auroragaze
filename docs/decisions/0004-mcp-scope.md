# 0004 — MCP exposes data and physics tools, not the composer

## Context

The MCP server makes AuroraGaze's capabilities available to any MCP client —
Claude Desktop, Cursor, internal ops dashboards. Two scope options exist:

1. Expose only the underlying tools (solar wind, Kp, visibility, drag,
   retrieval). The client orchestrates them.
2. Expose the full briefing as a single MCP tool that runs the whole
   six-node graph and returns the AuroraBriefing JSON.

## Decision

Option 1. Six tools: `get_solar_wind`, `get_kp_now`, `get_dst_now`,
`assess_visibility`, `compute_drag_delta_tool`, `retrieve_context`. No
end-to-end briefing tool over MCP.

## Consequences

- An MCP client (Claude Desktop in particular) gets the same primitives
  AuroraGaze's own agents use, and can compose them however it wants. The
  server is a *capability provider*, not a single black-box endpoint.
- This matches how MCP is intended to be used: small, well-scoped, typed
  tools that compose. A monolithic `generate_briefing` tool would be more
  convenient for one client but defeats the purpose of MCP.
- Latency: MCP tool calls are fast (no LLM). Each tool either hits NOAA,
  hits ChromaDB, or runs a pure function. p95 < 500 ms locally.
- No auth on MCP for the demo (stdio transport in Claude Desktop).
  Production-grade auth is out of scope for the portfolio version; an
  ADR captures the decision so the gap is explicit.
