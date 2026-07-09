"""Regression guards for the internal prompts.

The refusal-demo obligation of technique 07 lives in prompt text, not code,
so these tests pin the load-bearing phrases: the writer must include a
refusal example by default (not gated on refusal_matters), and the critic
must reject its absence.
"""

from app.pipeline import CRITIC_SYSTEM, WRITER_SYSTEM
from app.techniques import TECHNIQUES_BY_ID


def test_writer_requires_refusal_example_by_default():
    assert "MUST show an ambiguous or unanswerable input" in WRITER_SYSTEM
    assert "when in doubt, include it" in WRITER_SYSTEM
    # the obligation must not be conditioned on the refusal_matters flag
    writer_07 = WRITER_SYSTEM.split("- If 07:")[1].split("- If 08:")[0]
    assert "when the profile says refusal_matters" not in writer_07.split("Omit")[0]


def test_writer_allows_format_adapted_refusals():
    assert "adapted to the task's output format" in WRITER_SYSTEM


def test_critic_rejects_missing_refusal_example():
    assert "reject its absence" in CRITIC_SYSTEM
    assert "when in doubt, require" in CRITIC_SYSTEM
    assert "adapted to the output format" in CRITIC_SYSTEM


def test_catalog_07_apply_hint_carries_refusal_demo():
    hint = TECHNIQUES_BY_ID["07"].apply_hint
    assert "refusal" in hint
    assert "I don't know" in hint
