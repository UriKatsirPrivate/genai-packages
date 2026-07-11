# The 429 Optimizer: A Rate-Limit Ops Playbook Compressed Into One System Prompt

## Seven Resilience Strategies, One Gemini Call, No Backend

Teams scaling a GenAI application meet the same error: **HTTP 429 (Resource Exhausted)**. They rediscover the same fixes one production incident at a time: add a retry, add jitter to the retry, cache the giant context you've been re-sending on every call, fail over to another region, then add a rate limiter so the retries stop making things worse.

That's the idea behind the **429 Optimizer**, an open-source tool I built: instead of a human rediscovering these patterns at 3 a.m., an LLM acting as a Google Cloud AI architect applies the whole playbook at once, to *your* prompt and *your* code, and explains every decision, including the strategies it decided not to use.

Readers of my [Prompt Optimizer article](../../prompt-optimizer-8/articles/prompt-optimizer-from-first-principles.md) will notice the architecture went the other direction. That project is a four-agent pipeline with structured output and a revision loop. This one is a React page and a single Gemini call. There is no backend at all. The entire orchestration layer is a 25-line regex parser that splits one streamed response into tabs. The intelligence lives in one place: the system prompt.

## First Principles: What a 429 Is

Your quota is a budget of **requests per minute and tokens per minute, provisioned per model and per region**. A burst of traffic exhausts one of those budgets and the API starts refusing you until the window rolls over. A 429 reports budget exhaustion, nothing more mysterious than that.

Read it that way and the fixes stop being folklore. You can spend fewer tokens per request, send fewer requests, reach into other capacity pools (another region, another model, the global endpoint), or survive the seconds when a budget runs dry. The system prompt encodes seven strategies, each pulling one of those levers:

- **01. Smart Retries:** exponential backoff *with jitter*, so transient spikes pass without a thundering herd of synchronized retries
- **02. Global Model Routing:** quota is provisioned per region, so use the `global` endpoint and a regional failover loop to find capacity where it exists
- **03. Model Fallback:** quota pools are per model, so degrade from Pro to Flash during severe rate-limiting instead of failing
- **04. Context Caching:** stop re-sending the same 100,000-token document on every call; cache it once, reference it cheaply
- **05. Prompt Hygiene:** fewer tokens per request means more requests fit in the same tokens-per-minute budget
- **06. Traffic Shaping:** concurrency controls and rate limiters, so your own code stops manufacturing the spikes
- **07. Async Execution:** if the optimized code uses `asyncio`, it must still run where an event loop already exists; Jupyter gets a mandated `nest_asyncio` escape hatch

Only #01 is what most people ship. The retry buys time while the other six attack the cause.

## How It Works: One Call, Five Headings, a Regex Demultiplexer

You paste a prompt and a Python implementation (the page preloads a mock scenario: hundreds of concurrent calls, each re-sending the same huge policy document, the textbook context-caching case), toggle **Model Fallback** and **Regional Routing**, pick a model, and hit *Generate Artifacts*.

```
Your prompt + code + toggles (appended as ENABLED/DISABLED text)
   │
   ▼
One Gemini chat session (temperature 0.2, Google Search grounding)
   │
   ▼  a single streamed response, split live on five exact headings
① ## 1. Optimized Prompt ──────────────── rewritten for token efficiency
② ## 2. Optimized Code ────────────────── retries, caching, fallback, shaping
③ ## 3. 429 Error Reduction Report ────── every strategy, applied or not
④ ## 4. requirements.txt ──────────────── the exact dependencies
⑤ ## 5. Skill Files ───────────────────── a reusable SKILL.md agent skill
```

The output contract is those five markdown headings, verbatim. `parseArtifacts` in `src/lib/parser.ts` (five regexes, 25 lines) runs on the accumulating stream and routes each section into its own tab as the tokens arrive. You watch the optimized code materialize while the model is still writing the report. In the Prompt Optimizer, orchestration meant `asyncio.gather` and Pydantic schemas; here it means `[\s\S]*?` and a lookahead.

The user message turns the toggles into hard constraints. Disable Regional Routing and it tells the model: if a feature is DISABLED, do NOT include it in the optimized code. Because it's a chat, you iterate (*"make the backoff more aggressive"*, *"add async support"*) and the model re-emits the artifacts under the same headings. The UI merges each turn over the last (`parsed.code || prev.code`), so an artifact the model didn't re-emit keeps its previous value and the tabs never go blank mid-conversation.

One tab contains no LLM output at all. The **Integration Guide** is deterministic client code: it regex-sniffs the generated function's name and whether it's `async def`, then renders a matching FastAPI endpoint and a batch-processing example (`asyncio.gather` or a `ThreadPoolExecutor`, depending). A template gets that job done for free, so the app spends no tokens on it.

## The Report Covers Every Strategy, Including the Omitted Ones

Most code-generation tools hand you a diff and expect trust. Here the system prompt makes the report non-negotiable: it must address **all seven** named strategies (Smart Retries, Regional Failover, Global Model Routing, Model Fallback, Context Caching, Traffic Shaping, and Prompt Hygiene) and provide two things for each:

- **Implementation Detail**: the specific code snippets or line numbers where the strategy lives in the optimized code
- **Granular Impact Analysis**: what the strategy does to your 429 rate, and why

A strategy that doesn't apply to your case still appears in the report, with the reason for its omission. This is the same omission accounting the Prompt Optimizer enforces with its eight judges: the "no"s are half the value. *"Context caching skipped: your payload is under the 1,024-token minimum"* teaches you the boundary of the technique along with the technique itself.

## Fighting Staleness Two Ways

The hardest problem in generating SDK code is that model weights remember the `google-genai` SDK *vaguely*, and vaguely-remembered SDK code doesn't run. The system prompt fights that from both directions.

**First, it pastes the ground truth.** The prompt hard-codes the SDK's sharp edges instead of leaving them to recall: context caching takes `types.CreateCachedContentConfig(contents=[...])` passed as the `config` argument to `client.caches.create(model=..., config=...)`; TTL is `ttl="600s"`, not `ttl_seconds`; async calls go through `client.aio.models.generate_content`; parts come from `types.Part(text=...)` instead of `Part.from_text()`, wrapped in `types.Content(role="user", parts=[...])`. The prompt even pins the model names: the fallback chain must use Gemini 3 or 3.5 models, never `gemini-1.5` or `gemini-2.5`.

**Second, it grounds what it can't paste.** The prompt *requires* the model to use the Google Search tool to verify best practices and validate API parameters before emitting code, because rate-limit guidance and SDK surfaces change faster than training data.

The prompt also anticipates the failure modes production would otherwise teach you: caching needs a minimum of 1,024 tokens, so the generated code must include a try-except or a length check that falls back to standard non-cached calls when the context is too small.

The fifth artifact closes the loop. The generated **SKILL.md** (YAML frontmatter, trigger phrases, step-by-step workflow) packages the whole methodology as a reusable agent skill, so your coding agent can apply the same playbook to code it hasn't written yet.

## See It in Action

No setup required; a live instance runs here:

**[https://ratelimit.genaitools.cloud/](https://ratelimit.genaitools.cloud/)**

Hit *Generate Artifacts* on the preloaded example and watch it come back with a cached context, jittered backoff, traffic shaping, a Flash fallback, and a report tracing each decision to a quota mechanism.

## Under the Hood

The stack is small:

- **React + TypeScript + Vite + Tailwind**, a single-page app deployed as a Google AI Studio Build applet.
- **Gemini via the `@google/genai` SDK**, called from the browser: one `ai.chats.create` session with the architect system instruction, `temperature: 0.2`, and the `googleSearch` tool enabled. Models: `gemini-3.5-flash` by default, `gemini-3.1-pro-preview` selectable.
- **Streaming end-to-end**: one `sendMessageStream` call per turn feeds `parseArtifacts`, which updates the tabs token-by-token.
- **The Integration Guide is a template**, built client-side from the generated artifacts with no LLM call.

```bash
git clone https://github.com/UriKatsirPrivate/Vertex-AI-429-Optimizer.git
cd Vertex-AI-429-Optimizer
npm install

echo 'GEMINI_API_KEY=your_api_key_here' > .env
npm run dev
```

Then paste in the ugliest, most 429-prone loop you have.

## Conclusion: Resilience by Design

Teams write rate-limit handling the worst way: under pressure, one incident at a time, patch by patch. The playbook itself is stable (backoff with jitter, cache the context, shape the traffic, fall back across models and regions), and a stable playbook is what one well-engineered system prompt can apply consistently, provided you pin the SDK truth it would otherwise misremember and make it account for the strategies it skips.

The Prompt Optimizer needed four agents and a critic to earn trust. This one earns it with a contract: five headings, seven strategies, every verdict in the report. The code is open source in the [Vertex-AI-429-Optimizer repository](https://github.com/UriKatsirPrivate/Vertex-AI-429-Optimizer). Clone it, point it at Gemini, and let the playbook harden your calls before production does it for you.

---

*Disclaimer: This code is provided "as-is" as a demonstration only to illustrate a potential solution. The code does not constitute a Google product or service of any kind, and Google offers no support, warranties, or liability of any kind with its regard. Whoever chooses to use this code accepts all responsibility related to it, including for its implementation, use, and ongoing maintenance. For the avoidance of doubt, this code is not eligible for the Google Open Source Software Vulnerability Rewards Program.*
