"""Shared fixtures: a deterministic FakeLLM and pipeline wiring for tests."""

import pytest

from app.config import Settings
from app.models import (
    ChatReply,
    CriticCheck,
    CriticReport,
    TechniqueVerdict,
    UseCaseProfile,
    WriterOutput,
)
from app.pipeline import PromptOptimizer
from app.techniques import TECHNIQUES


class FakeLLM:
    """Duck-typed stand-in for app.llm.LLM with deterministic outputs.

    - Records every call as (schema.__name__, system, user) in self.calls.
    - Verdicts deliberately come back with a wrong technique_id ("99") and a
      wrong name, so tests can prove the pipeline overwrites both from the
      catalog.
    - Techniques in `irrelevant_ids` come back relevant=False but WITH a
      non-empty application, so tests can prove the pipeline blanks it.
    - The first `reject_critic_first_n` critic calls return approved=False
      with feedback; subsequent critic calls approve.
    - When `error` is set, every call raises it.
    """

    def __init__(
        self,
        *,
        reject_critic_first_n: int = 0,
        irrelevant_ids: tuple[str, ...] = ("04", "07"),
        error: Exception | None = None,
        chat_updated_prompt: str | None = None,
    ) -> None:
        self.reject_critic_first_n = reject_critic_first_n
        self.irrelevant_ids = set(irrelevant_ids)
        self.error = error
        self.chat_updated_prompt = chat_updated_prompt
        self.calls: list[tuple[str, str, str]] = []
        self._verdict_calls = 0
        self._writer_calls = 0
        self._critic_calls = 0

    def calls_for(self, schema_name: str) -> list[tuple[str, str, str]]:
        return [c for c in self.calls if c[0] == schema_name]

    async def generate_structured(self, *, system: str, user: str, schema: type):
        self.calls.append((schema.__name__, system, user))
        if self.error is not None:
            raise self.error
        if issubclass(schema, UseCaseProfile):
            return UseCaseProfile(
                summary="Summarize legal contracts into risk bullet points.",
                task_type="summarization",
                involves_math=False,
                involves_char_level=False,
                factual_recall_risk=True,
                source_text_available=True,
                pattern_teachable=True,
                reasoning_heavy=True,
                refusal_matters=True,
            )
        if issubclass(schema, TechniqueVerdict):
            return self._verdict(f"{system}\n{user}")
        if issubclass(schema, WriterOutput):
            self._writer_calls += 1
            return WriterOutput(
                design_notes=f"design notes for draft {self._writer_calls}",
                optimized_prompt=f"OPTIMIZED PROMPT (draft {self._writer_calls})",
            )
        if issubclass(schema, ChatReply):
            return ChatReply(
                reply="fake chat reply",
                updated_prompt=self.chat_updated_prompt,
            )
        if issubclass(schema, CriticReport):
            self._critic_calls += 1
            approved = self._critic_calls > self.reject_critic_first_n
            return CriticReport(
                checks=[
                    CriticCheck(
                        technique_id="01",
                        note="delimited context block present",
                        realized=True,
                    )
                ],
                feedback="" if approved else "Realize technique 02 explicitly.",
                approved=approved,
            )
        raise AssertionError(f"FakeLLM got unexpected schema: {schema!r}")

    def _verdict(self, text: str) -> TechniqueVerdict:
        self._verdict_calls += 1
        matched = {
            t.id for t in TECHNIQUES if f"Technique {t.id}" in text or t.name in text
        }
        if len(matched) == 1:
            tid = matched.pop()
        else:
            tid = TECHNIQUES[(self._verdict_calls - 1) % len(TECHNIQUES)].id
        relevant = tid not in self.irrelevant_ids
        return TechniqueVerdict(
            technique_id="99",
            reason=f"fake reasoning for technique {tid}",
            relevant=relevant,
            priority=2,
            application=(
                f"apply technique {tid} concretely"
                if relevant
                else "SHOULD BE BLANKED BY PIPELINE"
            ),
            name="Wrong Name From Model",
        )


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
def optimizer(fake_llm: FakeLLM, settings: Settings) -> PromptOptimizer:
    return PromptOptimizer(fake_llm, settings)
