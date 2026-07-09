# The Prompt Optimizer: A Multi-Agent Pipeline That Engineers Prompts From First Principles

## Stop Collecting Tricks, Start Applying Principles: Four Agents That Build — and Critique — Your Prompt

If you've spent any time in the GenAI world, you've seen the endless lists: "27 prompt engineering tips", "the one magic phrase that unlocks GPT". Most of them are folklore. The tips that actually work all trace back to a handful of facts about **how LLMs actually work** — and once you know the facts, you don't need the folklore anymore.

That's the idea behind the **Prompt Optimizer**, an open-source service I built: instead of a human remembering eight techniques and hand-weaving them into every prompt, a **multi-agent LLM pipeline** does it — and shows its reasoning for every decision, including the techniques it decided *not* to use.

You give it a use case (and optionally your existing prompt). It returns a production-ready optimized prompt, plus a full technique report explaining every choice.

## 🧠 Two Facts, Eight Techniques

Everything in the system is grounded in two facts from the talk *"How LLMs Actually Work — Prompting from First Principles"*:

- **Fact 01 (Memory):** weights remember vaguely; context remembers exactly. Knowledge in the parameters is like a book you read months ago — text in the prompt is working memory.
- **Fact 02 (Compute):** every token gets a small, fixed budget of thought. One token = one trip through the layers; no single pass can make a big leap.

And one corollary: capabilities are **Swiss cheese** — brilliant across whole domains, then failing on something trivial. So you check the work.

From these, eight techniques fall out:

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

Notice #07's twist: most few-shot advice tells you to demonstrate the *pattern*. But in-context learning copies **behavior**, not just format — so one of your examples should demonstrate the *refusal*. Show the model an unanswerable input met with "I don't know", and it learns restraint along with the format.

## 🤖 The Pipeline: Four Agents, One Prompt

The service is itself an LLM application — a four-stage pipeline running on **Gemini**, where every stage is a single structured LLM call with one narrowly scoped job:

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

**① The Analyzer** reads your use case and profiles it honestly: does it involve exact math? Character-level work? Is there a factual-recall risk? Would a confident wrong answer be costly? It's explicitly instructed to be conservative — a flag is set only when the task genuinely calls for it.

**② The Judges** are where it gets interesting. Instead of one model deciding which techniques apply, **eight judges run in parallel**, each receiving exactly one technique's card — its first principle, rule of thumb, and relevance heuristics. Each judge answers a single question: *does the mechanism this technique addresses actually bear on THIS task?* Judging from the first principle, not vibes. And each judge is told that **an honest "no" beats a padded prompt** — a marginal fit gets a low priority, an irrelevant technique gets skipped, with the reasoning recorded either way.

**③ The Writer** receives only the selected techniques (with the judges' application notes) and weaves them into **one coherent prompt** — no redundancy, no bolted-on checklist. Each technique carries hard, non-negotiable obligations: if technique 01 is selected, the prompt must contain a delimited context slot with an explicit `{{PLACEHOLDER}}`; if 07 is selected, the examples must be fully written out, refusal demo included.

**④ The Critic** is the pipeline's own quality gate. It checks every selected technique independently and only counts it as realized if the prompt text *would actually cause the intended behavior* — a vague mention isn't enough. "Show your calculation" doesn't satisfy "compute with code". A working section that only exists in the output format doesn't satisfy "demand step-by-step reasoning". If any check fails, the critic writes concrete rewrite instructions and the writer produces a new draft — a **bounded revision loop**, so a stubborn disagreement can't spin forever.

## 📋 Every Verdict, Including the "No"s

Most optimization tools hand you a result and expect trust. This one reports **all eight verdicts** — applied *and* skipped — each with the judge's reasoning:

```jsonc
{
  "optimized_prompt": "...",            // ready to use
  "use_case_profile": { ... },          // analyzer output
  "techniques": [                       // all 8, each with a reason
    { "technique_id": "01", "relevant": true,  "priority": 1, "reason": "...", "application": "..." },
    { "technique_id": "05", "relevant": false, "reason": "..." }
  ],
  "critic": { "approved": true, "checks": [ ... ] },
  "revised": false,                     // true if the critic forced a rewrite
  "design_notes": "..."
}
```

The skipped techniques are half the value. When the judge says *"technique 05 isn't relevant — nothing in this task is character-level"*, you're learning the boundaries of the technique, not just consuming a prompt.

Beyond the one-shot endpoint, the service also has:

- **`POST /optimize/stream`** — an NDJSON progress stream, one event per line: watch the analyzer finish, the eight judges report in, the writer draft, the critic approve (or reject and force a revision) in real time.
- **`POST /chat`** — a follow-up assistant that receives the complete run context (profile, verdicts, critic report, technique catalog, current prompt). Ask it *why* a technique was skipped, or ask for a modification — it returns the complete revised prompt, and warns you (citing the technique number) if your request would weaken one.

## 🪞 The Pipeline Practices What It Preaches

My favorite part of building this: the pipeline is **built with the same eight techniques it applies**.

- Every judge receives the full technique card in its context rather than relying on what the model "knows" about prompting — that's technique 01, *paste the source*.
- Every LLM-facing Pydantic model puts its `reason` field **before** its verdict field, so the model spends tokens thinking before it commits to an answer — that's technique 03, *answer last, not first*, enforced at the schema level.
- The critic is the pipeline's own verification pass — technique 08, *own the output*, as an architectural component instead of a human habit.

Prompt engineering advice that can't survive being applied to itself probably isn't advice worth taking.

## ☁️ Under the Hood

The stack is deliberately small:

- **Python + FastAPI**, with the optimizer built lazily at startup — importing the app requires no API key.
- **Gemini via the `google-genai` SDK** — works with a plain `GEMINI_API_KEY` or against **Vertex AI** with application-default credentials (`GOOGLE_GENAI_USE_VERTEXAI=true`).
- **Pydantic structured output** for every stage — the analyzer, judges, writer, critic, and chat agent all return validated, typed objects. No JSON parsing of free text, anywhere.
- **`asyncio.gather`** for the judge fan-out — eight LLM calls in the time of one.
- A single dataclass catalog (`techniques.py`) is the **source of truth** for the eight techniques; technique ids and names in verdicts are always overwritten from it, never trusted from model output.

And the whole pipeline is testable **without an API key**: the test suite runs against a fake LLM, so the orchestration logic — parallel judging, the revision loop, the streaming protocol — is verified deterministically in CI.

```bash
git clone https://github.com/UriKatsirPrivate/genai-packages.git
cd genai-packages/prompt-optimizer
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

export GEMINI_API_KEY=...
.venv/bin/uvicorn app.main:app --reload
```

Then throw a lazy prompt at it:

```bash
curl -s localhost:8000/optimize \
  -H 'content-type: application/json' \
  -d '{
        "use_case": "Answer questions about figures in quarterly earnings reports, including growth calculations. Wrong numbers are costly.",
        "existing_prompt": "What was the revenue and how much did it grow?"
      }' | jq .
```

Watch it come back with a delimited context slot, a mandatory step-by-step working section, code-for-math instructions, an explicit "I don't know" permission, a refusal-demo few-shot example, and a self-verification step — each one traceable to a first principle, each one checked by the critic.

## Conclusion: Encode the Why, Not the Tips

Prompt tips age badly; first principles don't. Tokenizers will change, models will get smarter, but *"context remembers exactly"* and *"every token gets a fixed budget of thought"* will keep explaining why the techniques work — and when they don't apply.

The Prompt Optimizer is my attempt to encode that: not a template library, but a system that **reasons about your task from first principles** and shows its work at every step.

The code is open source in the [genai-packages repository](https://github.com/UriKatsirPrivate/genai-packages) — clone it, point it at Gemini, and let four agents argue about your prompt so you don't have to.

Ready to optimize?
