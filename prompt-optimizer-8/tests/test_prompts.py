"""Regression guards for the internal prompts.

The refusal-demo obligation of technique 07 lives in prompt text, not code,
so these tests pin the load-bearing phrases: the writer must include a
refusal example by default (not gated on refusal_matters), and the critic
must reject its absence.
"""

from app.pipeline import CHAT_SYSTEM, CRITIC_SYSTEM, WRITER_SYSTEM
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


def test_writer_requires_search_tool_instruction_for_06():
    writer_06 = WRITER_SYSTEM.split("- If 06:")[1].split("- If 07:")[0]
    assert "BOTH mandatory" in writer_06
    assert "web-search" in writer_06
    assert "I don't know" in writer_06
    # pasted context must not be accepted as a substitute for the search half
    assert "not the search half" in writer_06


def test_critic_rejects_missing_search_tool_instruction_for_06():
    assert "TWO required halves" in CRITIC_SYSTEM
    assert "web-search" in CRITIC_SYSTEM
    assert "reject the" in CRITIC_SYSTEM
    assert "does NOT" in CRITIC_SYSTEM


def test_catalog_06_apply_hint_carries_search_tool():
    hint = TECHNIQUES_BY_ID["06"].apply_hint
    assert "web-search" in hint
    assert "I don't know" in hint


def _writer_section(tid: str) -> str:
    nxt = f"{int(tid) + 1:02d}"
    tail = WRITER_SYSTEM.split(f"- If {tid}:")[1]
    return tail.split(f"- If {nxt}:")[0] if f"- If {nxt}:" in tail else tail


def test_writer_obligations_are_mandatory_and_non_cancelling():
    assert "MANDATORY" in WRITER_SYSTEM
    assert "never removes an obligation" in WRITER_SYSTEM
    assert "cancel another" in WRITER_SYSTEM


def test_writer_01_placeholder_and_only_from_material():
    w = _writer_section("01")
    assert "{{PLACEHOLDER}}" in w
    assert "ONLY from that material" in w
    assert "never" in w and "memory" in w


def test_writer_02_reasoning_demanded_not_permitted():
    w = _writer_section("02")
    assert "demanded, not merely permitted" in w
    assert "answer-only" in w


def test_writer_03_verdict_last_in_every_format():
    w = _writer_section("03")
    assert "AFTER the working" in w
    assert "per-item" in w


def test_writer_04_code_required_with_fallback():
    w = _writer_section("04")
    assert "mental arithmetic explicitly forbidden" in w
    assert "digit-by-digit" in w
    assert '"Show your calculation" alone does not satisfy' in w


def test_writer_05_char_level_routed_to_code():
    w = _writer_section("05")
    assert "routed to code" in w
    assert "tokenizer hides" in w


def test_writer_08_concrete_self_verification():
    w = _writer_section("08")
    assert "CONCRETE self-verification" in w
    assert "names what to re-check" in w
    assert "not enough" in w


def test_audit_hardening_phrases_present():
    # writer side
    assert "UNCONDITIONAL" in WRITER_SYSTEM  # 02: no model-judged gates
    assert "leaves no room" in WRITER_SYSTEM  # 02: structural squeezes too
    assert "written AND run" in WRITER_SYSTEM  # 05: not just described
    assert "human-verification note" in WRITER_SYSTEM  # 08: human half
    # critic side
    assert "re-licenses answering" in CRITIC_SYSTEM  # 01: contradiction clause
    assert "does not by itself satisfy 02" in CRITIC_SYSTEM  # 02 vs 03 overlap
    assert "verdict alone" in CRITIC_SYSTEM  # 03: answer-only formats
    assert "no-code runtime does not excuse" in CRITIC_SYSTEM  # 04
    assert "softeners are a rejection" in CRITIC_SYSTEM  # 06b: required, not may
    assert "no refusal option" in CRITIC_SYSTEM  # 06a: contradiction clause
    assert "nonsensical exception does not apply" in CRITIC_SYSTEM  # 07 gate
    assert "off-task or toy examples are a rejection" in CRITIC_SYSTEM  # 07
    assert "non-refusal demonstration" in CRITIC_SYSTEM  # 07 count/mix
    assert "human-verification note" in CRITIC_SYSTEM  # 08


def test_chat_code_rules_default_to_gemini():
    assert "never announce code without including it" in CHAT_SYSTEM
    assert "google-genai" in CHAT_SYSTEM
    assert "genai.Client()" in CHAT_SYSTEM
    assert "legacy" in CHAT_SYSTEM  # warns off the old google-generativeai SDK
    assert "unless the user explicitly names another provider" in CHAT_SYSTEM


def test_critic_has_reject_rule_per_technique():
    assert "reject if either is missing" in CRITIC_SYSTEM  # 01
    assert "merely permitted" in CRITIC_SYSTEM  # 02
    assert "leads with the verdict" in CRITIC_SYSTEM  # 03
    assert '"show your calculation" without code is a rejection' in CRITIC_SYSTEM  # 04
    assert "inspection is a rejection" in CRITIC_SYSTEM  # 05
    assert "TWO required halves" in CRITIC_SYSTEM  # 06
    assert "reject its absence" in CRITIC_SYSTEM  # 07
    assert '"double-check your work" line is a rejection' in CRITIC_SYSTEM  # 08
    assert "does not automatically satisfy another" in CRITIC_SYSTEM
