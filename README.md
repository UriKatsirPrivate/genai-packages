# genai-packages

A monorepo of GenAI packages and demos. Each package lives in its own directory with its own README, dependencies, and tests.

## Packages

| Package | Description |
|---------|-------------|
| [`prompt-optimizer-8`](prompt-optimizer-8/) | FastAPI service that turns a use case (and optionally an existing prompt) into an optimized prompt plus a technique report. Itself a multi-agent Gemini pipeline (analyzer → 8 parallel technique judges → prompt writer → critic), built on the eight techniques from *"How LLMs Actually Work — Prompting from First Principles"*. |

## Quick start

```bash
cd prompt-optimizer-8
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

export GEMINI_API_KEY=...        # or GOOGLE_GENAI_USE_VERTEXAI=true + gcloud ADC
.venv/bin/uvicorn app.main:app --reload

./demo.sh                        # exercise the API against the running server
.venv/bin/python -m pytest       # tests run against a fake LLM — no API key needed
```

See [`prompt-optimizer-8/README.md`](prompt-optimizer-8/README.md) for the full API, environment variables, and design notes.

## Repo tooling

- `run.sh` — launches Claude Code against Vertex AI (sets the Vertex env vars, exports macOS keychain root CAs for Node so corporate-proxy TLS works, then runs `npx @anthropic-ai/claude-code`).
- `setup-data-sharing.sh` — one-time GCP setup: enables Anthropic publisher data sharing on a project, a prerequisite for gated Claude models on Vertex AI. Safe to re-run.

## License

[MIT](LICENSE)
