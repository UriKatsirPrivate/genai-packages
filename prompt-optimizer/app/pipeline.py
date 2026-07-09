"""The runtime multi-agent pipeline: analyzer -> 8 parallel technique judges
-> prompt writer -> critic, with a bounded revision loop.

Each stage is one structured LLM call. The system prompts below are the heart
of the service — each one is scoped to a single job and grounded in the deck's
two facts (weights remember vaguely, context remembers exactly; every token
gets a fixed budget of thought).
"""

import asyncio

from .config import Settings
from .llm import LLM
from .models import (
    CriticReport,
    OptimizeRequest,
    OptimizeResponse,
    TechniqueVerdict,
    UseCaseProfile,
    WriterOutput,
)
from .techniques import TECHNIQUES, TECHNIQUES_BY_ID, Technique, technique_card


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

Hard requirements for optimized_prompt:
- Structure it in clearly delimited sections.
- If technique 01 is selected: include a delimited context slot containing \
the placeholder {{SOURCE_TEXT}} and instruct the model to answer ONLY from \
that text.
- If 02 or 03: require step-by-step working with intermediate results \
written out, and put the final answer LAST in a clearly marked section — \
never first.
- If 04 or 05: explicitly instruct the model to use code for math / for any \
character-level operation, never mental arithmetic or inspection.
- If 06: explicitly permit answering "I don't know" when the answer is not \
in the provided material, and note that a search/grounding tool is \
recommended.
- If 07: include 2-4 concrete, fully written input->output examples matching \
the real task; when the profile says refusal_matters, one example must show \
an unanswerable input answered with "I don't know".
- If 08: end with a self-verification step (re-check the answer against the \
source and requirements before finishing).
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
enough. Verify the specifics: technique 01 needs a delimited {{SOURCE_TEXT}} \
slot with an answer-only-from-it instruction; 02/03 need visible working with \
the final answer last; 04/05 need explicit use-code instructions; 06 needs \
explicit permission to say "I don't know" AND a note recommending a \
search/grounding tool; 07 needs fully written input->output examples, and \
when the profile says refusal_matters, one example must show an unanswerable \
input answered with "I don't know"; 08 needs a final self-verification step.

Set approved=true only if every check is realized. When rejecting, write \
feedback as concrete rewrite instructions — what to add, where, and in what \
wording — not general commentary.\
"""


class PromptOptimizer:
    def __init__(self, llm: LLM, settings: Settings):
        self._llm = llm
        self._settings = settings

    @property
    def settings(self) -> Settings:
        return self._settings

    async def optimize(self, req: OptimizeRequest) -> OptimizeResponse:
        profile = await self._analyze(req)
        verdicts = await self._judge_all(req, profile)
        selected = sorted(
            (v for v in verdicts if v.relevant),
            key=lambda v: (v.priority, v.technique_id),
        )

        writer = await self._write(req, profile, selected)
        critic = await self._critique(writer.optimized_prompt, profile, selected)

        revisions = 0
        while not critic.approved and revisions < self._settings.max_critic_revisions:
            revisions += 1
            writer = await self._write(
                req,
                profile,
                selected,
                previous_draft=writer.optimized_prompt,
                feedback=critic.feedback,
            )
            critic = await self._critique(writer.optimized_prompt, profile, selected)

        return OptimizeResponse(
            optimized_prompt=writer.optimized_prompt,
            use_case_profile=profile,
            techniques=sorted(verdicts, key=lambda v: v.technique_id),
            critic=critic,
            revised=revisions > 0,
            design_notes=writer.design_notes,
            model=self._settings.model,
        )

    async def _analyze(self, req: OptimizeRequest) -> UseCaseProfile:
        blocks = [_block("USE CASE", req.use_case)]
        if req.existing_prompt:
            blocks.append(_block("EXISTING PROMPT", req.existing_prompt))
        return await self._llm.generate_structured(
            system=ANALYZER_SYSTEM, user=_join(*blocks), schema=UseCaseProfile
        )

    async def _judge_all(
        self, req: OptimizeRequest, profile: UseCaseProfile
    ) -> list[TechniqueVerdict]:
        raw = await asyncio.gather(
            *(self._judge(t, req, profile) for t in TECHNIQUES)
        )
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
