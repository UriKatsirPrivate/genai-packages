# Article Ideas — Backlog

Compiled 2026-07-10 from a three-agent scout: portfolio mining (local projects + GitHub), workflow mining (Claude Code setup), and market research (HN/dev.to demand signals, July 2026).

Published so far in the series:
- [Prompt Optimizer — from first principles](prompt-optimizer-8/articles/prompt-optimizer-from-first-principles.md) (4-agent pipeline)
- [429 Optimizer — resilience by design](vertex-ai-429-optimizer/articles/429-optimizer-resilience-by-design.md) (one system prompt, no backend)
- [AI Skill Creator — encode the spec twice](ai-skill-creator/articles/encode-the-spec-twice.md) (structured output + deterministic validator)

Series thesis so far: **match the architecture to the failure mode** (4 agents → 1 call → 1 call + validator).

---

## Top three (material ready + proven market gap)

### 1. "Catalog vs. Pipeline: Two Ways to Build a Prompt Improver" — GenAI / App Dev
- **Thesis:** the Prompt Playground (14 tools, human picks the technique, one templated call each) is the before-state of the Prompt Optimizer (judges pick the technique, critic verifies). When do you actually need a pipeline?
- **Evidence:** `~/Projects/vertex-prompt-playground` (registry-driven — 12 of 14 tools share one generic endpoint; live at myprompt.online) vs. `prompt-optimizer-8`. Confession beat: three of Fine-Tune's four "variants" are the same template at temperature 1.0 — variance sampling, not four techniques.
- **Market:** architecture-decision honesty is the one agent-adjacent format still hitting 300+ HN points; "single-call vs. pipeline" is nearly unwritten in 2026. Add token/latency/cost tables from both deployed apps.
- **Effort:** zero build work. **Recommended next.**

### 2. The definitive Gemini cost/quota engineering post — GenAI / GCP
- **Thesis:** the two kinds of 429 (quota-cap vs. rate-limit need different cooldowns), context caching economics, batch API, Flash-Lite routing, key hygiene — with real production numbers.
- **Evidence:** the 429 Optimizer app/article as a starting point; genaitools.cloud apps in production; Vertex AI experience.
- **Market:** the strongest demand signal found — Gemini API horror stories everywhere ($82k stolen-key bill, $128k near-bankruptcy Reddit thread, press attention), yet no definitive Gemini-specific piece exists. Live news peg.
- **Effort:** needs pulling real numbers from production projects.

### 3. "I Mined 78 Sessions of My Own Claude Code History" — Productivity
- **Thesis:** a 200-line Python script distilled every transcript into stats and findings; the diagnosis ("you do the hard part well and pay for the easy part repeatedly") got implemented, measurably.
- **Evidence:** `~/Projects/claude-code-on-vertex/cc-history-analysis/` — `extract.py`, `stats.json` (883 Bash / 489 Edit / 49 agent spawns), `findings.json` (`implementedCount: 6`, 2026-06-23). The current `~/.claude/CLAUDE.md` is the checkable after-state (`/push`, pinned notebook IDs, Playwright-first rule). Brutal details: "commit and push" hand-typed 24+ times (twice as "commiy"); a 283-prompt slide-cosmetics session; 14 near-identical WebFetch subagents for one factual question.
- **Market:** "I measured X with hard numbers" is a top-traveling format.
- **Effort:** fully ready, nothing to build.

## Strong seconds (timely, some assembly required)

### 4. "One Skill, Three Runtimes" — GenAI
- **Thesis:** port real Claude Code skills (fact-check, notebooklm, stop-slop) to Gemini CLI and GitHub Copilot; report exactly what breaks.
- **Market:** agentskills.io lists ~40 adopting runtimes; Google is rolling Skills into Gemini/AI Studio (April 2026). Nobody has published a first-hand cross-runtime account; the Gemini side is nearly untouched.
- **Effort:** skills exist; the ports are the work.

### 5. "I Actually Ship From AI Studio Build" — App Dev
- **Thesis:** the honest counterpart to Google's vibe-code-to-production marketing — what survives contact with production (service-worker key proxy, custom domains, Firebase coupling, per-user quota paths) and what doesn't.
- **Evidence:** five of the seven genaitools.cloud apps are AI Studio Build applets; the proxy mechanics are already documented from the 2026-07-10 investigations.
- **Market:** underserved — community content is mostly outage complaints and one key-exposure writeup.
- **Effort:** material largely in hand; needs first-person deployment war stories.

### 6. "The App That Works With the Model Off" — App Dev
- **Thesis:** the PCA exam trainer's feedback layer treats the LLM as garnish, not meal — deterministic rule-based insights always run; the LLM enriches best-effort behind a Vertex → direct-Anthropic → rules-only fallback chain (`LLM_PROVIDER=none` is a supported mode).
- **Evidence:** `~/Projects/gcp-pca-exam/src/lib/feedback/` — cache keyed on `latestAnswerAt`, refresh rate-limited to 60s, input capped at 200 answers / output at 700 tokens. Bonus: passwordless Cloud SQL IAM auth.
- **Fit:** natural fourth series entry — 4 agents → 1 call → 1 call + validator → 0 *required* calls.
- **Effort:** ready; app deployed on Cloud Run + Cloud SQL.

## Quick wins (narrow but distinctive; Claude Code audience)

### 7. "/push Also Garbage-Collects My Permissions" — Productivity
Every push classifies local allowlist grants into Promote / Keep local / Drop / Never promote, generalizes one-offs to family wildcards (`Bash(kill 65428)` → `Bash(kill *)`), and deletes an emptied local config. Nobody treats the allowlist as managed state. Evidence: `~/.claude/commands/push.md` steps 7–8; 153 accreted global allows.

### 8. "Deny Rules Can't See Chained Commands" — Productivity
Prefix-matched deny rules are blind to `cd x && rm -rf y` and `psql -c "DROP DATABASE"`. Real safety is three layers: deny rules for the honest case, a PreToolUse hook regex over the whole command string for the sneaky case, CLAUDE.md habits (`find -delete`, never `-rf`) so the agent doesn't even try. Evidence: `~/.claude/hooks/block-destructive.sh`. Short, sharp, copyable.

### 9. "Adversarial Fact-Checkers for My Own Blog Posts" — Productivity / GenAI
The 2026-07-10 publishing pipeline: bundle-grepping investigator agents → writer agents → independent fact-checkers verifying every quote character-for-character against source/deployed bundles before push. **Caution:** anti-AI-slop sentiment is hostile terrain — must lead with the verification mechanics, not the AI authorship.

## Bench (viable, weaker or needs prep)

- **"Every App I Build Now Exports a Skill"** — SKILL.md as the packaging format across three apps (429 Optimizer, Migration Assistant, Skill Creator); series capstone; also absorbs Migration Tool coverage.
- **"Parallel Agents Don't Need Locks, They Need Ownership"** — the `=== YOUR FILES (create only these) ===` dispatch-time file-ownership contract that built the 7-feature PCA app collision-free.
- **"Encode the Spec Twice, Content Edition"** — the PCA app's deterministic content gate (Zod schemas, answer-key checks) + production telemetry as second verifier; sequel to the Skill Creator piece.
- **"The Rewrite: Streamlit to a Registry"** — phased cutover, `streamlit-final` rollback tag, the per-thread genai client fix for concurrent-request 502s; could fold into #1.
- **"Same Claude, Different Door"** — Claude Code via Vertex AI in a corporate GCP shop: three env vars plus two undocumented traps (`data_sharing_enabled_provider` gate, macOS keychain root-CA export). The script is copy-pasted across five repos — that's the hook.
- **"A Deck Is One HTML File; The Cost Is Your Adjectives"** — single-file HTML decks are trivial to generate; iteration language is the real spend (the 283-prompt session; saving the "what should my initial prompt have been" answer back into the repo).
- **"My CLAUDE.md Is Decision Procedures, Not Preferences"** — if-then defaults (UI bug → reproduce with Playwright first; research → one /deep-research, cap manual lookups at 2 agreeing sources) vs. style-rule CLAUDE.md advice.
- **"NotebookLM, Three Ways"** — raw Python script vs. FastAPI dashboard vs. MCP server over the same unofficial surface. Needs `nblm-api` cleanup first; credit `teng-lin/notebooklm-py`; ToS-gray.
- **JS-bundle teardown of a deployed AI product** — the H1-2026 viral genre (teardowns of AI tools people use daily). Don't teach the technique; pick a target people care about (e.g., what AI Studio Build apps actually ship to the client). Overlaps #5.

## Skip list (saturated or dead markets)

- Multi-agent framework posts, MCP explainers — saturated to dead on HN.
- Prompt-engineering tips — dead; only measured token/context economics travels.
- Standalone Migration Tool article — structurally repeats the 429 piece; absorb into "Every App Exports a Skill".
- Generic Claude Code tips listicles — absent from anything that traveled in 2026.

## Format notes (from market research)

- Personal blogs on custom domains dominate HN; Medium is absent from top GenAI stories. dev.to is mid-tier (first-person failure narratives do best there).
- Winning formats, in order: investigation/teardown of a daily-use tool; "I measured X" with hard numbers; postmortem honesty; architecture-decision posts with failures included; contrarian "you're using X wrong".
- Timely hooks (July 2026): Skills rolling into the Gemini ecosystem; the Gemini API key-theft wave ($82k/$128k); Claude 5 family + Gemini 3.5 Flash still in the vibe-review window.
