"""The eight techniques from 'How LLMs Actually Work — Prompting from First
Principles' (how-llms-work.html), as a machine-usable catalog.

Everything here is grounded in the deck's two facts:
  Fact 01 (Memory)  — weights remember vaguely; context remembers exactly.
  Fact 02 (Compute) — every token gets a small, fixed budget of thought.
and their corollary: capabilities have blind spots, so you check the work.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Technique:
    id: str
    name: str
    principle: str  # which fact it falls out of
    rule: str  # the deck's rule of thumb, verbatim spirit
    when: str  # relevance heuristics for the judge
    apply_hint: str  # how it typically shows up in an optimized prompt


TECHNIQUES: tuple[Technique, ...] = (
    Technique(
        id="01",
        name="Paste the source (context is working memory)",
        principle=(
            "Fact 01 — knowledge in the parameters is a vague recollection, "
            "like a book read months ago; text in the prompt is working "
            "memory, directly available."
        ),
        rule=(
            "Provide, don't recall: paste the source under a delimiter — the "
            "smallest text that fully contains the answer."
        ),
        when=(
            "The task depends on specific documents, data, code, or records "
            "the user has or can obtain (summarize X, answer from Y, extract "
            "from Z). Not relevant for pure generation with no source."
        ),
        apply_hint=(
            "Add a clearly delimited context section (e.g. a <context> block "
            "or --- fences) with a placeholder for the source text, and "
            "instruct the model to answer ONLY from that text."
        ),
    ),
    Technique(
        id="02",
        name="Give it tokens to think",
        principle=(
            "Fact 02 — one token = one trip through a fixed stack of layers; "
            "no single pass can make a big leap, so reasoning must be spread "
            "across many tokens."
        ),
        rule=(
            "Distribute reasoning across many tokens — ask for intermediate "
            "results, step by step."
        ),
        when=(
            "Multi-step reasoning, analysis, planning, non-trivial "
            "transformation. Marginal for trivial rewording or lookups."
        ),
        apply_hint=(
            "Instruct: work step by step, write each intermediate result "
            "before moving on."
        ),
    ),
    Technique(
        id="03",
        name="Answer last, not first",
        principle=(
            "Fact 02 — demanding the answer first forces the whole problem "
            "into a single forward pass; everything printed afterwards is "
            "post-hoc justification."
        ),
        rule=(
            "Drop 'answer in a single token'. Let it write the steps; the "
            "final answer comes last, not first."
        ),
        when=(
            "Any task ending in a short verdict, number, label, or decision. "
            "Especially when an existing prompt says 'reply with only X'."
        ),
        apply_hint=(
            "Order the output format: reasoning/working first, final answer "
            "in a marked section at the end. Never demand answer-only output "
            "for hard tasks."
        ),
    ),
    Technique(
        id="04",
        name="Use code for math",
        principle=(
            "A neural net doing arithmetic is a person doing it in their "
            "head — any intermediate step can silently slip. The interpreter "
            "runs outside the network with real correctness guarantees."
        ),
        rule=(
            "Add 'use code' — make it write and run code instead of trusting "
            "mental arithmetic."
        ),
        when=(
            "Arithmetic, aggregation, percentages/growth rates, dates, unit "
            "conversions, anything numeric that must be exact."
        ),
        apply_hint=(
            "Instruct the model to compute all numeric results with code "
            "(e.g. Python) rather than in its head; if the runtime has no "
            "code tool, tell it to show explicit digit-by-digit working."
        ),
    ),
    Technique(
        id="05",
        name="Use code for perception tasks (it sees tokens, not characters)",
        principle=(
            "Tokenization packs characters into sealed chunks before the "
            "model runs — the letters simply aren't there to count. A "
            "perception gap, not a reasoning gap; prompting harder can't "
            "restore what the tokenizer removed."
        ),
        rule=(
            "Spot the perception tasks — spelling, counting characters, "
            "'every third letter' — and route them to code, which sees "
            "characters."
        ),
        when=(
            "Character-level work: spelling, counting letters/words "
            "exactly, string slicing, format validation by character."
        ),
        apply_hint=(
            "Instruct that any character-level operation must be done with "
            "code, never by inspection."
        ),
    ),
    Technique(
        id="06",
        name="Ground it + allow 'I don't know'",
        principle=(
            "Models are statistical token tumblers that imitate the "
            "confident tone of training answers — when they don't know, "
            "they fabricate rather than admit it. Hallucination is the "
            "default, not a glitch."
        ),
        rule=(
            "Enable web search (it pulls real text into working memory) and "
            "explicitly allow 'I don't know' — prompt it: don't guess, say so."
        ),
        when=(
            "Factual recall risk: entity facts, current events, figures, "
            "citations — anything the model would answer from weights and a "
            "confident wrong answer is costly."
        ),
        apply_hint=(
            "Add an explicit permission to answer 'I don't know' when the "
            "answer isn't in the provided context or search results, AND an "
            "instruction to use a web-search/retrieval tool when one is "
            "available to pull real source text into working memory."
        ),
    ),
    Technique(
        id="07",
        name="Few-shot the pattern (and the refusal)",
        principle=(
            "In-context learning: reading input->output examples, the model "
            "infers the algorithm and continues it — it copies behavior, "
            "not just format, including restraint."
        ),
        rule=(
            "Show several input->output pairs before the real query. "
            "Sharpest use: seed a refusal demo so the model copies "
            "'I don't know' instead of guessing."
        ),
        when=(
            "Format- or style-sensitive outputs, classification, "
            "transformation with a learnable pattern; add a refusal demo "
            "whenever unanswerable inputs are possible."
        ),
        apply_hint=(
            "Include 2-4 concrete input->output examples matching the real "
            "task, one of which shows an ambiguous or unanswerable input "
            "met with an explicit refusal ('I don't know', or a refusal "
            "label fitting the output format) — omit the refusal demo only "
            "when it would be outright nonsensical for the task."
        ),
    ),
    Technique(
        id="08",
        name="Own the output (the Swiss-cheese rule)",
        principle=(
            "Capabilities are Swiss cheese: brilliant across whole domains, "
            "then failing on something trivial. The holes are real and "
            "unpredictable."
        ),
        rule=(
            "Use them as tools in the toolbox, check their work, and own "
            "the product of your work. Great for first drafts; always verify."
        ),
        when=(
            "Always relevant to some degree; priority rises with stakes "
            "(production, money, health, legal, published output)."
        ),
        apply_hint=(
            "Add a final self-verification step to the prompt (re-check the "
            "answer against the source/requirements before finishing), and "
            "surface a human-verification note for high-stakes outputs."
        ),
    ),
)


TECHNIQUES_BY_ID: dict[str, Technique] = {t.id: t for t in TECHNIQUES}


def technique_card(t: Technique) -> str:
    """Render one technique as a compact brief for an LLM judge/writer."""
    return (
        f"Technique {t.id} — {t.name}\n"
        f"First principle: {t.principle}\n"
        f"Rule of thumb: {t.rule}\n"
        f"Typically relevant when: {t.when}\n"
        f"How it shows up in a prompt: {t.apply_hint}"
    )
