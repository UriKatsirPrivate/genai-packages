# prompt-optimizer-8

A FastAPI service that takes a **use case** (and optionally an **existing prompt**) and returns an **optimized prompt** plus a technique report — built on the eight techniques from the talk *"How LLMs Actually Work — Prompting from First Principles"*.

The service is itself a multi-agent LLM pipeline (Gemini via `google-genai`):

```
POST /optimize
   │
   ▼
① Analyzer ──────────── classifies the use case (UseCaseProfile)
   │
   ▼
② 8 Technique Judges ── run in parallel (asyncio.gather), one per technique;
   │                    each judges relevance from the technique's first principle
   ▼
③ Prompt Writer ─────── weaves the selected techniques into one coherent prompt
   │
   ▼
④ Critic ────────────── checks every selected technique is actually realized;
                        bounded revision loop back to ③ if not
```

## The eight techniques

| # | Technique | First principle |
|---|-----------|-----------------|
| 01 | Paste the source | Weights recall vaguely; context is working memory |
| 02 | Give it tokens to think | Fixed compute per token — spread reasoning across tokens |
| 03 | Answer last, not first | Answer-first forces the whole problem into one forward pass |
| 04 | Use code for math | Mental arithmetic slips silently; the interpreter doesn't |
| 05 | Use code for perception | The model sees tokens, not characters |
| 06 | Ground + allow "I don't know" | Hallucination is the default, not a glitch |
| 07 | Few-shot the pattern (and the refusal) | In-context learning copies behavior, including restraint |
| 08 | Own the output | Capabilities are Swiss cheese — check the work |

The response always reports **all eight** verdicts — applied and skipped — each with the judge's reasoning, so you see *why* a technique was or wasn't used.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

export GOOGLE_CLOUD_PROJECT=...  # Vertex AI only; gcloud auth application-default login for local ADC
export GOOGLE_CLOUD_LOCATION=global
.venv/bin/uvicorn app.main:app --reload

./demo.sh                        # exercise the API against the running server
```

Environment variables:

| Var | Default | |
|-----|---------|---|
| `GOOGLE_CLOUD_PROJECT` | — | required, Vertex AI project |
| `GOOGLE_CLOUD_LOCATION` | — | required; 3.x models need `global` |
| `GEMINI_MODEL` | `gemini-3.8-flash` | any Gemini model id |
| `GEMINI_TEMPERATURE` | `0.2` | |

## Call it

```bash
curl -s localhost:8000/optimize \
  -H 'content-type: application/json' \
  -d '{
        "use_case": "Extract quarterly revenue figures from earnings reports and compute quarter-over-quarter growth",
        "existing_prompt": "What was the revenue and how much did it grow?"
      }' | jq .
```

Response shape:

```jsonc
{
  "use_case": "...",                    // echoed from the request
  "existing_prompt": null,              // echoed from the request, if any
  "optimized_prompt": "...",            // ready to use
  "use_case_profile": { ... },          // analyzer output
  "techniques": [                       // all 8, each with reason
    { "technique_id": "01", "relevant": true,  "priority": 1, "reason": "...", "application": "..." },
    { "technique_id": "05", "relevant": false, "reason": "..." }
  ],
  "critic": { "approved": true, "checks": [ ... ] },
  "revised": false,                     // true if the critic forced a rewrite
  "design_notes": "...",
  "model": "gemini-3.8-flash"
}
```

`GET /health` for liveness (`/healthz` is kept as an alias, but Cloud Run's frontend intercepts that path on `*.run.app`).

## Tests

No API key needed — the pipeline is tested against a fake LLM:

```bash
.venv/bin/python -m pytest
```

## Design notes

- **The pipeline practices what it preaches.** Judges receive the full technique card in context (technique 01 — provide, don't recall); every LLM-facing Pydantic model puts its `reason` field *before* its verdict field so the model spends tokens thinking before committing (technique 03); the critic is the pipeline's own verification pass (technique 08).
- `app/techniques.py` is the single source of truth for the catalog; verdict `technique_id`/`name` are always overwritten from it, never trusted from model output.
- The critic revision loop is bounded by `Settings.max_critic_revisions` (default 1).

## Repo tooling

- `run.sh` — launches Claude Code against Vertex AI (sets the Vertex env vars, exports macOS keychain root CAs for Node so corporate-proxy TLS works, then runs `npx @anthropic-ai/claude-code`).
- `setup-data-sharing.sh` — one-time GCP setup: enables Anthropic publisher data sharing on a project, a prerequisite for gated Claude models on Vertex AI. Safe to re-run.

## License

[MIT](LICENSE)
