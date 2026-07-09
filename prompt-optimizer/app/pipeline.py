"""The runtime multi-agent pipeline: analyzer -> 8 parallel technique judges
-> prompt writer -> critic, with a bounded revision loop.

Each stage is one structured LLM call. The system prompts below are the heart
of the service — each one is scoped to a single job and grounded in the deck's
two facts (weights remember vaguely, context remembers exactly; every token
gets a fixed budget of thought).
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from .config import Settings
from .llm import LLM
from .models import (
    ChatReply,
    ChatRequest,
    CriticReport,
    OptimizeRequest,
    OptimizeResponse,
    TechniqueVerdict,
    UseCaseProfile,
    WriterOutput,
)
from .techniques import TECHNIQUES, TECHNIQUES_BY_ID, Technique, technique_card


ProgressCallback = Callable[[dict[str, Any]], Awaitable[None]]


async def _no_progress(event: dict[str, Any]) -> None:
    return None


def _block(label: str, body: str) -> str:
    return f"=== {label} ===\n{body.strip()}\n=== END {label} ==="


def _join(*blocks: str) -> str:
    return "\n\n".join(blocks)


ANALYZER_SYSTEM = """\
You are an expert use-case analyst for LLM applications. Given a use case \
(and possibly an existing prompt), classify the task honestly — do not \
flatter it or assume capabilities it does not need.

Ground every flag in what the task actually requires:
- involves_math: arithmetic, dates, aggregation, or unit work that must be exact.
- involves_char_level: spelling, counting characters, exact string manipulation.
- factual_recall_risk: the answer depends on facts the model would recall from \
its weights rather than from provided text.
- source_text_available: the user has, or could paste, the documents/data the \
task depends on.
- pattern_teachable: the output format or style could be taught with a few \
input->output examples.
- reasoning_heavy: multi-step reasoning, not lookup or rewording.
- refusal_matters: a confident wrong answer is costly; "I don't know" is a \
valid and desirable outcome.

Be conservative: set a flag true only when the use case genuinely calls for \
it. Restate the use case in one paragraph, in your own words, as the summary.\
"""

JUDGE_SYSTEM = """\
You are a relevance judge for exactly ONE prompting technique. You receive \
that technique's card, a use case, an optional existing prompt, and an \
analyst's profile of the task.

Judge from the technique's FIRST PRINCIPLE, not vibes: does the mechanism it \
addresses (vague weight memory, fixed per-token compute, tokenizer \
perception, hallucination under uncertainty, in-context pattern copying, \
unpredictable blind spots) actually bear on THIS task? Reason it out first, \
then decide.

Be willing to say not relevant — an honest "no" beats a padded prompt. A \
marginal fit is priority 4-5; a load-bearing fit is priority 1-2.

When relevant, 'application' must be a concrete, prompt-ready instruction \
tailored to this use case — something a prompt writer could paste in nearly \
verbatim. When not relevant, leave application empty.\
"""

WRITER_SYSTEM = """\
You are an expert prompt engineer. Produce ONE complete, ready-to-use prompt \
that realizes every selected technique, grounded in how LLMs actually work: \
weights remember vaguely, context remembers exactly; every token gets a \
fixed budget of thought.

Every selected technique's obligation below is MANDATORY. An application \
note adds task-specific detail but never removes an obligation. Never let \
one technique's wording cancel another's — a brevity demand must not \
suppress step-by-step working, and pasted context must not replace the \
search-tool instruction.

Hard requirements for optimized_prompt:
- Structure it in clearly delimited sections.
- If 01: include a clearly delimited context slot for EVERY source the task \
needs, each containing an UPPERCASE {{PLACEHOLDER}} (e.g. {{SOURCE_TEXT}}), \
plus an explicit instruction to answer ONLY from that material and never \
from memory.
- If 02: REQUIRE intermediate results to be written out step by step — \
reasoning must be demanded, not merely permitted, and the demand must be \
UNCONDITIONAL (a gate the model judges itself, like "if complex", counts \
as merely permitted). Never pair it with an answer-only or keep-it-brief \
demand, or any format, schema, or length constraint that leaves no room \
for the working; the output format itself must contain an explicit \
working/intermediate-results section.
- If 03: every output format the prompt defines — global AND per-item — \
must place the final answer/verdict in a clearly marked section AFTER the \
working. Never first, never alone.
- If 04: all arithmetic and numeric results MUST be computed by writing and \
running code — mental arithmetic explicitly forbidden. The prompt text \
itself must carry BOTH the write-and-run-code instruction AND an in-prompt \
fallback clause requiring explicit digit-by-digit written working when no \
code tool is available. "Show your calculation" alone does not satisfy \
this.
- If 05: any character-level operation (spelling, counting characters or \
words, slicing, per-character validation) MUST be routed to code that is \
written AND run — describing code without executing it does not count, and \
inspection never does: the tokenizer hides characters from the model.
- If 06: two obligations, BOTH mandatory. (a) Explicitly permit answering \
"I don't know" when the answer is not in the provided material — never \
guess. (b) Include an explicit grounding instruction addressed to the \
model: if a web-search or retrieval tool is available, USE it to pull the \
relevant source text into context and cite what it finds; fall back to \
"I don't know" only when neither the provided material nor a tool can \
supply the fact. Do not drop (b) because source text is pasted in — pasted \
material realizes technique 01, not the search half of 06.
- If 07: include 2-4 concrete, fully written input->output examples matching \
the real task — no placeholders or ellipses, each following the exact \
output format the prompt itself defines. One of them MUST show an ambiguous \
or unanswerable input answered with an explicit refusal — "I don't know", \
"cannot determine", or a refusal adapted to the task's output format (e.g. \
an "Undetermined" label for classification) — because in-context learning \
copies restraint, not just format. Omit the refusal example ONLY if it \
would be outright nonsensical for this task; when in doubt, include it. \
When the profile says refusal_matters, it is never optional.
- If 08: end with a CONCRETE self-verification step that names what to \
re-check, covering the risk surfaces of the other selected techniques \
(answer vs. source when 01 is selected, calculations recomputed when 04/05 \
are, requirements met otherwise), before the final answer is finalized — a \
generic "double-check your work" line is not enough. When the use case is \
high-stakes (production, money, health, legal, published output), also \
include an explicit human-verification note: the output must be reviewed \
by a human before it is acted on.
- Weave the techniques into one coherent prompt — no redundancy, no \
bolted-on checklist.

When an existing prompt is provided, improve it: preserve its intent, domain \
specifics, and any constraints that still make sense.

If critic feedback is provided, apply every instruction in it to the \
previous draft.

In design_notes, briefly state how each selected technique was realized.\
"""

CRITIC_SYSTEM = """\
You are a strict prompt critic. You receive an optimized prompt, the \
use-case profile, and the techniques the prompt was supposed to realize, \
each with its card and application note.

Produce exactly one check per selected technique: point to where in the \
prompt text the technique is actually realized, or state that it is missing \
or only nominally present. A technique counts as realized only if the prompt \
text itself would cause the intended behavior — a vague mention is not \
enough. Check each technique independently: text that satisfies one \
obligation does not automatically satisfy another.

Verify the specifics, and reject when any of them fail:
- 01 needs a clearly delimited context slot with an explicit {{PLACEHOLDER}} \
for each required source AND an answer-only-from-this-material instruction; \
reject if either is missing, and reject if any other instruction in the \
prompt re-licenses answering from general knowledge or memory when the \
material is silent.
- 02 needs an explicit, UNCONDITIONAL instruction to work step by step and \
write each intermediate result before moving on. Reasoning merely permitted, \
gated on the model's own judgment ("if complex", "when non-trivial"), or \
contradicted by an answer-only/brevity demand or any format, schema, or \
length constraint that leaves no room for the working — each is a \
rejection. A working section required only by the output format does not \
by itself satisfy 02.
- 03 needs the final answer/verdict marked, placed LAST, and preceded by the \
required working in every output format the prompt defines, including \
per-item formats; any format that leads with the verdict, or consists of \
the verdict alone, is a rejection.
- 04 needs the prompt text itself to carry BOTH an explicit instruction to \
compute all numeric work by writing and RUNNING code AND an in-prompt \
digit-by-digit written fallback clause for when no code tool is available; \
reject if either clause is absent — an assumed no-code runtime does not excuse \
the code instruction, and "show your calculation" without code is a rejection.
- 05 needs character-level operations explicitly routed to code that is \
written AND run — describing code without executing it does not count; \
leaving spelling/counting to inspection is a rejection.
- 06 has TWO required halves — (a) explicit permission to say "I don't \
know" and (b) an explicit instruction to use a web-search/retrieval tool \
when one is available — and you must reject the draft if either half is \
missing (pasted source material does NOT substitute for the search-tool \
instruction). Half (b) must REQUIRE tool use when a tool is available — \
"you may search" / "consider searching" softeners are a rejection. Reject \
half (a) when the refusal permission is contradicted elsewhere: an \
always-answer demand, or a closed output label set with no refusal option.
- 07 needs 2-4 fully written input->output examples (no placeholders or \
ellipses, matching the prompt's own output format AND drawn from the actual \
task domain — off-task or toy examples are a rejection), at least one being \
a normal non-refusal demonstration of the pattern, INCLUDING one where an \
ambiguous or unanswerable input is met with an explicit refusal — "I don't \
know", "cannot determine", or a refusal adapted to the output format (e.g. \
an "Undetermined" label) — and you must reject its absence unless a refusal \
example would be outright nonsensical for this task (when in doubt, require \
it). When the profile says refusal_matters, the nonsensical exception does \
not apply — a missing refusal example is always a rejection.
- 08 needs a concrete final self-verification step whose named checks cover \
the risk surfaces of the selected techniques (source fidelity when 01 is \
selected, recomputed numbers when 04/05 are, requirements coverage \
otherwise) — a generic "double-check your work" line is a rejection. When \
the use case is high-stakes, 08 also needs an explicit human-verification \
note; self-verification alone does not satisfy it there.

Set approved=true only if every check is realized. When rejecting, write \
feedback as concrete rewrite instructions — what to add, where, and in what \
wording — not general commentary.\
"""


CHAT_SYSTEM = """\
You are the follow-up assistant for a completed prompt-optimization run. You \
receive the full run context — use case, profile, all technique verdicts, \
critic report, the technique catalog, and the CURRENT optimized prompt — \
plus the conversation so far. The last conversation turn is the one to \
answer.

You have two jobs:
1. Answer questions about the result. Ground every answer in the provided \
context and the technique cards' first principles — never invent facts \
about the run that are not in the context.
2. Apply requested modifications. When the user asks for a change, set \
updated_prompt to the COMPLETE revised prompt — never a fragment, diff, or \
summary. Preserve every realized technique unless the user explicitly asks \
to drop one; if the request weakens a technique, comply where sensible but \
say so in reply, citing the technique number.

Set updated_prompt ONLY when the user asked for a modification; otherwise \
leave it null. Keep reply concise (no markdown headers), and when you \
changed the prompt, summarize what changed in reply.

Code rules for reply: when the user asks for code, reply MUST contain the \
complete, runnable code inside ``` fences — never announce code without \
including it. Code samples default to Python with the google-genai SDK for \
Gemini unless the user explicitly names another provider or language. \
Canonical Gemini call (current SDK — do not use the legacy \
google-generativeai package):

    from google import genai

    client = genai.Client()  # reads GEMINI_API_KEY; GOOGLE_GENAI_USE_VERTEXAI=true for Vertex
    resp = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=filled_prompt,
    )
    print(resp.text)\
"""


class PromptOptimizer:
    def __init__(self, llm: LLM, settings: Settings):
        self._llm = llm
        self._settings = settings

    @property
    def settings(self) -> Settings:
        return self._settings

    async def optimize(
        self,
        req: OptimizeRequest,
        progress: ProgressCallback | None = None,
    ) -> OptimizeResponse:
        emit = progress or _no_progress

        await emit({"event": "stage", "stage": "analyzer", "status": "running"})
        profile = await self._analyze(req)
        await emit(
            {
                "event": "stage",
                "stage": "analyzer",
                "status": "done",
                "task_type": profile.task_type,
            }
        )

        await emit(
            {
                "event": "stage",
                "stage": "judges",
                "status": "running",
                "total": len(TECHNIQUES),
            }
        )
        verdicts = await self._judge_all(req, profile, emit)
        selected = sorted(
            (v for v in verdicts if v.relevant),
            key=lambda v: (v.priority, v.technique_id),
        )
        await emit(
            {
                "event": "stage",
                "stage": "judges",
                "status": "done",
                "applied": len(selected),
            }
        )

        draft = 1
        await emit(
            {"event": "stage", "stage": "writer", "status": "running", "draft": draft}
        )
        writer = await self._write(req, profile, selected)
        await emit(
            {"event": "stage", "stage": "writer", "status": "done", "draft": draft}
        )
        await emit(
            {"event": "stage", "stage": "critic", "status": "running", "round": draft}
        )
        critic = await self._critique(writer.optimized_prompt, profile, selected)
        await emit(
            {
                "event": "stage",
                "stage": "critic",
                "status": "done",
                "round": draft,
                "approved": critic.approved,
            }
        )

        revisions = 0
        while not critic.approved and revisions < self._settings.max_critic_revisions:
            revisions += 1
            draft += 1
            await emit(
                {
                    "event": "stage",
                    "stage": "writer",
                    "status": "running",
                    "draft": draft,
                }
            )
            writer = await self._write(
                req,
                profile,
                selected,
                previous_draft=writer.optimized_prompt,
                feedback=critic.feedback,
            )
            await emit(
                {"event": "stage", "stage": "writer", "status": "done", "draft": draft}
            )
            await emit(
                {
                    "event": "stage",
                    "stage": "critic",
                    "status": "running",
                    "round": draft,
                }
            )
            critic = await self._critique(writer.optimized_prompt, profile, selected)
            await emit(
                {
                    "event": "stage",
                    "stage": "critic",
                    "status": "done",
                    "round": draft,
                    "approved": critic.approved,
                }
            )

        return OptimizeResponse(
            optimized_prompt=writer.optimized_prompt,
            use_case_profile=profile,
            techniques=sorted(verdicts, key=lambda v: v.technique_id),
            critic=critic,
            revised=revisions > 0,
            design_notes=writer.design_notes,
            model=self._settings.model,
        )

    async def chat(self, req: ChatRequest) -> ChatReply:
        blocks = [_block("USE CASE", req.use_case)]
        if req.existing_prompt:
            blocks.append(
                _block("ORIGINAL PROMPT (before optimization)", req.existing_prompt)
            )
        blocks.append(
            _block(
                "USE-CASE PROFILE",
                req.result.use_case_profile.model_dump_json(indent=2),
            )
        )
        blocks.append(
            _block(
                "TECHNIQUE VERDICTS",
                json.dumps(
                    [v.model_dump() for v in req.result.techniques], indent=2
                ),
            )
        )
        blocks.append(
            _block("CRITIC REPORT", req.result.critic.model_dump_json(indent=2))
        )
        blocks.append(
            _block(
                "TECHNIQUE CATALOG",
                "\n\n".join(technique_card(t) for t in TECHNIQUES),
            )
        )
        blocks.append(
            _block("CURRENT OPTIMIZED PROMPT", req.result.optimized_prompt)
        )
        blocks.append(
            _block(
                "CONVERSATION",
                "\n\n".join(f"{m.role.upper()}: {m.content}" for m in req.messages),
            )
        )
        return await self._llm.generate_structured(
            system=CHAT_SYSTEM, user=_join(*blocks), schema=ChatReply
        )

    async def _analyze(self, req: OptimizeRequest) -> UseCaseProfile:
        blocks = [_block("USE CASE", req.use_case)]
        if req.existing_prompt:
            blocks.append(_block("EXISTING PROMPT", req.existing_prompt))
        return await self._llm.generate_structured(
            system=ANALYZER_SYSTEM, user=_join(*blocks), schema=UseCaseProfile
        )

    async def _judge_all(
        self,
        req: OptimizeRequest,
        profile: UseCaseProfile,
        emit: ProgressCallback = _no_progress,
    ) -> list[TechniqueVerdict]:
        done = 0
        lock = asyncio.Lock()

        async def judge_and_report(t: Technique) -> TechniqueVerdict:
            nonlocal done
            v = await self._judge(t, req, profile)
            async with lock:
                done += 1
                await emit(
                    {
                        "event": "judge_done",
                        "technique_id": t.id,
                        "name": t.name,
                        "relevant": v.relevant,
                        "priority": v.priority,
                        "done": done,
                        "total": len(TECHNIQUES),
                    }
                )
            return v

        raw = await asyncio.gather(*(judge_and_report(t) for t in TECHNIQUES))
        verdicts: list[TechniqueVerdict] = []
        for t, v in zip(TECHNIQUES, raw):
            update: dict[str, str] = {"technique_id": t.id, "name": t.name}
            if not v.relevant:
                update["application"] = ""
            verdicts.append(v.model_copy(update=update))
        return verdicts

    async def _judge(
        self, technique: Technique, req: OptimizeRequest, profile: UseCaseProfile
    ) -> TechniqueVerdict:
        blocks = [
            _block("TECHNIQUE UNDER JUDGMENT", technique_card(technique)),
            _block("USE CASE", req.use_case),
        ]
        if req.existing_prompt:
            blocks.append(_block("EXISTING PROMPT", req.existing_prompt))
        blocks.append(_block("USE-CASE PROFILE", profile.model_dump_json(indent=2)))
        return await self._llm.generate_structured(
            system=JUDGE_SYSTEM, user=_join(*blocks), schema=TechniqueVerdict
        )

    async def _write(
        self,
        req: OptimizeRequest,
        profile: UseCaseProfile,
        selected: list[TechniqueVerdict],
        previous_draft: str | None = None,
        feedback: str | None = None,
    ) -> WriterOutput:
        blocks = [_block("USE CASE", req.use_case)]
        if req.existing_prompt:
            blocks.append(
                _block("EXISTING PROMPT TO IMPROVE", req.existing_prompt)
            )
        blocks.append(_block("USE-CASE PROFILE", profile.model_dump_json(indent=2)))
        for v in selected:
            card = technique_card(TECHNIQUES_BY_ID[v.technique_id])
            blocks.append(
                _block(
                    f"SELECTED TECHNIQUE {v.technique_id} (priority {v.priority})",
                    f"{card}\nApplication note: {v.application}",
                )
            )
        if previous_draft is not None:
            blocks.append(_block("PREVIOUS DRAFT", previous_draft))
        if feedback:
            blocks.append(_block("CRITIC FEEDBACK", feedback))
        return await self._llm.generate_structured(
            system=WRITER_SYSTEM, user=_join(*blocks), schema=WriterOutput
        )

    async def _critique(
        self,
        optimized_prompt: str,
        profile: UseCaseProfile,
        selected: list[TechniqueVerdict],
    ) -> CriticReport:
        blocks = [
            _block("OPTIMIZED PROMPT", optimized_prompt),
            _block("USE-CASE PROFILE", profile.model_dump_json(indent=2)),
        ]
        for v in selected:
            card = technique_card(TECHNIQUES_BY_ID[v.technique_id])
            blocks.append(
                _block(
                    f"SELECTED TECHNIQUE {v.technique_id}",
                    f"{card}\nApplication note: {v.application}",
                )
            )
        return await self._llm.generate_structured(
            system=CRITIC_SYSTEM, user=_join(*blocks), schema=CriticReport
        )
