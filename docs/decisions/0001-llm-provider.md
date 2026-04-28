# 0001 — DeepSeek as default LLM, not Anthropic

## Context

AuroraGaze runs one to two LLM calls per briefing (composer, optionally a
ReAct sub-agent for analogue search) and uses an LLM-as-judge for the eval
gate. At the operating volumes we expect (10 to 50 briefings per day in
demo, hundreds during eval runs), the per-token cost dominates the bill.

Choices considered: Anthropic Claude (Sonnet / Haiku), OpenAI GPT, DeepSeek
V3 (`deepseek-chat`), Ollama-hosted local model.

## Decision

DeepSeek V3 (`deepseek-chat`) as the default. MiniMax M2 documented as an
alternative path through the same factory. Ollama for offline development.
A single `make_llm()` reads `LLM_PROVIDER` from env and returns the right
`BaseChatModel`; nothing else in the codebase mentions a provider.

## Consequences

- Per-token cost is roughly an order of magnitude below Claude Sonnet and
  half of Claude Haiku, which is what makes the eval gate affordable on
  every PR.
- Tool-calling and structured-output behaviour is solid in DeepSeek V3;
  fewer schema-violation retries than smaller open-source models.
- We are not locked in: swapping `LLM_PROVIDER=ollama` returns a working
  ChatOllama instance against the same prompts. Anti-vendor-lock-in by
  construction.
- Risk: DeepSeek's billing model is prepaid wallet (we hit a 402 on the
  first end-to-end run because the wallet was empty). Mitigation: a CI
  smoke test runs against Ollama, not DeepSeek, so build never blocks on
  external balance.
- Anthropic dependency is explicitly avoided in `requirements.txt` and in
  `CLAUDE.md`'s "never do" list. The portfolio choice is to demonstrate
  provider-agnostic engineering.
