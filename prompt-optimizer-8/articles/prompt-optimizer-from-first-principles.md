# The Prompt Optimizer: A Multi-Agent Pipeline That Engineers Prompts From First Principles

## Four Agents That Build and Critique Your Prompt

If you've spent any time in the GenAI world, you've seen the endless lists: "27 prompt engineering tips", "the one magic phrase that unlocks GPT". Most of them are folklore. The tips that work trace back to a handful of facts about how LLMs process text, and once you know the facts, you don't need the folklore.

That's the idea behind the **Prompt Optimizer**, an open-source service I built: instead of a human remembering eight techniques and hand-weaving them into each prompt, a **multi-agent LLM pipeline** does it, and shows its reasoning for every decision, including the techniques it decided *not* to use.

You give it a use case (and optionally your existing prompt). It returns a production-ready optimized prompt, plus a full technique report explaining every choice.

## Two Facts, Eight Techniques

Everything in the system rests on two facts from the talk *"How LLMs Actually Work — Prompting from First Principles"*:

- **Fact 01 (Memory):** weights remember vaguely; context remembers exactly. Knowledge in the parameters is like a book you read months ago; text in the prompt is working memory.
- **Fact 02 (Compute):** every token gets a small, fixed budget of thought. One token = one trip through the layers; no single pass can make a big leap.

And one corollary: capabilities are **Swiss cheese**, brilliant across whole domains, then failing on something trivial. So you check the work.

From these, eight techniques fall out:

- **01. Paste the source:** weights recall vaguely; context is working memory
- **02. Give it tokens to think:** compute per token is fixed, so spread reasoning across tokens
- **03. Answer last, not first:** answer-first forces the whole problem into one forward pass
- **04. Use code for math:** mental arithmetic slips without warning; the interpreter doesn't
- **05. Use code for perception:** the model sees tokens, not characters
- **06. Ground + allow "I don't know":** hallucination is the default, not a glitch
- **07. Few-shot the pattern (and the refusal):** in-context learning copies behavior, including restraint
- **08. Own the output:** capabilities are Swiss cheese, so check the work

Technique 07 has a twist. Most few-shot advice tells you to demonstrate the *pattern*, but in-context learning copies **behavior**, format included. One of your examples should demonstrate the *refusal*: show the model an unanswerable input met with "I don't know", and it learns restraint along with the format.

## The Pipeline: Four Agents, One Prompt

The service is itself an LLM application: a four-stage pipeline running on **Gemini**, where every stage is a single structured LLM call with one narrow job:

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
④ Critic ────────────── checks every selected technique is realized;
                        bounded revision loop back to ③ if not
```

**① The Analyzer** reads your use case and profiles it against concrete flags: exact math, character-level work, factual-recall risk, the cost of a confident wrong answer. Its instructions demand conservatism: raise a flag only when the task calls for it.

**② The Judges.** Instead of one model deciding which techniques apply, **eight judges run in parallel**, each receiving one technique's card: its first principle, rule of thumb, and relevance heuristics. Each judge answers a single question from that first principle: does the mechanism this technique addresses bear on THIS task? The card also tells the judge that **an honest "no" beats a padded prompt**, so a marginal fit gets a low priority and an irrelevant technique gets skipped, with the reasoning recorded either way.

**③ The Writer** receives only the selected techniques (with the judges' application notes) and weaves them into **one coherent prompt**, with no redundancy and no bolted-on checklist. Each technique carries hard, non-negotiable obligations: if the judges selected technique 01, the prompt must contain a delimited context slot with an explicit `{{PLACEHOLDER}}`; if they selected 07, the examples must be written out in full, refusal demo included.

**④ The Critic** is the pipeline's own quality gate. It checks each selected technique on its own and counts it as realized only if the prompt text would cause the intended behavior; a vague mention fails. "Show your calculation" doesn't satisfy "compute with code". A working section that only exists in the output format doesn't satisfy "demand step-by-step reasoning". If any check fails, the critic writes concrete rewrite instructions and the writer produces a new draft. The revision loop is **bounded**, so a stubborn disagreement can't spin forever.

## Every Verdict, Including the "No"s

Most optimization tools hand you a result and expect trust. This one reports **all eight verdicts**, applied and skipped, each with the judge's reasoning:

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

The skipped techniques are half the value. When the judge says *"technique 05 isn't relevant: nothing in this task is character-level"*, you learn the boundary of the technique along with the prompt.

Beyond the one-shot endpoint, the service also has:

- **`POST /optimize/stream`**: an NDJSON progress stream, one event per line. Watch the analyzer finish, the eight judges report in, the writer draft, and the critic approve (or reject and force a revision) in real time.
- **`POST /chat`**: a follow-up assistant that receives the complete run context (profile, verdicts, critic report, technique catalog, current prompt). Ask it why it skipped a technique, or ask for a modification; it returns the complete revised prompt and warns you (citing the technique number) if your request would weaken one.

## The Pipeline Practices What It Preaches

My favorite part of building this: the pipeline uses the same eight techniques it applies.

- Every judge receives the full technique card in its context rather than relying on what the model "knows" about prompting: technique 01, *paste the source*.
- Every LLM-facing Pydantic model puts its `reason` field **before** its verdict field, so the model spends tokens thinking before it commits to an answer: technique 03, *answer last, not first*, enforced at the schema level.
- The critic is the pipeline's own verification pass: technique 08, *own the output*, as an architectural component instead of a human habit.

Prompt engineering advice that can't survive its own application isn't worth taking.

## See It in Action

No setup required; a live instance runs on Cloud Run:

**[https://prompt-optimizer-8-854735162550.me-west1.run.app/](https://prompt-optimizer-8-854735162550.me-west1.run.app/)**

Paste a use case (and optionally your existing prompt), watch the eight judges report in live, and read every verdict, including the techniques the pipeline decided to skip.

## Under the Hood

The stack is small:

- **Python + FastAPI**, with the optimizer built lazily at startup; importing the app requires no API key.
- **Gemini via the `google-genai` SDK**, which works with a plain `GEMINI_API_KEY` or against **Vertex AI** with application-default credentials (`GOOGLE_GENAI_USE_VERTEXAI=true`).
- **Pydantic structured output** for every stage: the analyzer, judges, writer, critic, and chat agent all return validated, typed objects. No JSON parsing of free text, anywhere.
- **`asyncio.gather`** for the judge fan-out: eight LLM calls in the time of one.
- A single dataclass catalog (`techniques.py`) is the **source of truth** for the eight techniques; the pipeline overwrites technique ids and names in verdicts from the catalog instead of trusting model output.

The whole pipeline is testable **without an API key**: the test suite runs against a fake LLM, so CI verifies the orchestration logic (parallel judging, the revision loop, the streaming protocol) deterministically.

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

Watch it come back with a delimited context slot, a mandatory step-by-step working section, code-for-math instructions, an explicit "I don't know" permission, a refusal-demo few-shot example, and a self-verification step, each one traceable to a first principle and checked by the critic.

## Conclusion: Encode the Why, Not the Tips

Prompt tips age; first principles don't. Tokenizers will change and models will get smarter, but *"context remembers exactly"* and *"every token gets a fixed budget of thought"* will keep explaining why the techniques work, and when they don't apply.

The Prompt Optimizer is my attempt to encode that: a system that **reasons about your task from first principles** and shows its work at every step.

The code is open source in the [genai-packages repository](https://github.com/UriKatsirPrivate/genai-packages). Clone it, point it at Gemini, and let four agents argue about your prompt so you don't have to.

---

*Disclaimer: This code is provided "as-is" as a demonstration only to illustrate a potential solution. The code does not constitute a Google product or service of any kind, and Google offers no support, warranties, or liability of any kind with its regard. Whoever chooses to use this code accepts all responsibility related to it, including for its implementation, use, and ongoing maintenance. For the avoidance of doubt, this code is not eligible for the Google Open Source Software Vulnerability Rewards Program.*
