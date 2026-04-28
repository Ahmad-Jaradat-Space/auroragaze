# Deploy notes

## Default: Fly.io

The simplest path. One command from a clean checkout, given `flyctl` and a
Fly account:

```
fly launch --copy-config --no-deploy
fly secrets set DEEPSEEK_API_KEY=sk-...
fly deploy
```

The image bakes in:
- the embedding model (`bge-small-en-v1.5`),
- the reranker (`bge-reranker-v2-m3`),
- the corpus ingested into a persistent ChromaDB at `/app/data/chroma`.

Cold start: about 8 to 12 seconds while the model files load. Warm: p50
under 1.5 s for `/api/snapshot`, p50 under 6 s for a full streamed
briefing (one DeepSeek call dominates).

## Alternative: Hetzner CX22 box

A €5/month CX22 (2 vCPU, 4 GB RAM, 40 GB SSD) handles this with room
to spare. Same Dockerfile; behind Caddy or Nginx for TLS. Used for
v0.3-style cost discipline once Fly.io's free tier is exceeded.

```
docker build -t auroragaze .
docker run -d --name auroragaze --restart unless-stopped \
  -p 8080:8080 \
  -e DEEPSEEK_API_KEY=sk-... \
  auroragaze
```

## Costs

- Fly.io free tier covers a single shared-2x machine and one auto-stop
  app. AuroraGaze fits that envelope while traffic is portfolio-level.
- DeepSeek wallet: $5 covers ~5,000 briefings at the current prompt size.
- Total: zero infra, ~$0.001 per briefing for the LLM call.
