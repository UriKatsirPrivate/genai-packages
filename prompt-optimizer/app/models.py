"""Pydantic contracts shared by the pipeline, the API layer, and the tests.

Field order inside the LLM-facing models is deliberate: reasoning fields come
BEFORE verdict fields, so the model spends tokens thinking before it commits
to an answer (technique #03 — answer last, not first — applied to ourselves).
"""

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------
# Stage 1 — use-case analyzer output
# --------------------------------------------------------------------------
class UseCaseProfile(BaseModel):
    summary: str = Field(description="One-paragraph restatement of the use case")
    task_type: str = Field(
        description="e.g. summarization, extraction, qa, classification, "
        "generation, codegen, math, agent"
    )
    involves_math: bool = Field(description="Arithmetic, dates, aggregation, units")
    involves_char_level: bool = Field(
        description="Spelling, counting characters, exact string manipulation"
    )
    factual_recall_risk: bool = Field(
        description="Depends on facts the model would have to recall from weights"
    )
    source_text_available: bool = Field(
        description="The user has (or could paste) source documents/data"
    )
    pattern_teachable: bool = Field(
        description="Output format/style could be taught with input->output examples"
    )
    reasoning_heavy: bool = Field(
        description="Requires multi-step reasoning rather than lookup or rewriting"
    )
    refusal_matters: bool = Field(
        description="A wrong-but-confident answer is costly; 'I don't know' is a "
        "valid and desirable outcome"
    )


# --------------------------------------------------------------------------
# Stage 2 — per-technique relevance judge output (one judge per technique,
# run in parallel)
# --------------------------------------------------------------------------
class TechniqueVerdict(BaseModel):
    technique_id: str = Field(description="'01'..'08', echoed from the brief")
    reason: str = Field(
        description="Why this technique does or does not apply to this use case, "
        "reasoned from the technique's first principle"
    )
    relevant: bool
    priority: int = Field(
        default=3, ge=1, le=5, description="1 = most important, 5 = marginal"
    )
    application: str = Field(
        default="",
        description="Concrete instruction for how to realize this technique in "
        "THIS prompt (empty when not relevant)",
    )
    # Filled from the catalog by the pipeline, never trusted from the model:
    name: str = ""


# --------------------------------------------------------------------------
# Stage 3 — prompt writer output
# --------------------------------------------------------------------------
class WriterOutput(BaseModel):
    design_notes: str = Field(
        description="How the selected techniques were woven into the prompt"
    )
    optimized_prompt: str = Field(description="The complete, ready-to-use prompt")


# --------------------------------------------------------------------------
# Stage 4 — critic output
# --------------------------------------------------------------------------
class CriticCheck(BaseModel):
    technique_id: str
    note: str = Field(description="Where/how the technique is (or isn't) realized")
    realized: bool


class CriticReport(BaseModel):
    checks: list[CriticCheck]
    feedback: str = Field(
        default="",
        description="Actionable rewrite instructions when not approved",
    )
    approved: bool


# --------------------------------------------------------------------------
# API request / response
# --------------------------------------------------------------------------
class OptimizeRequest(BaseModel):
    use_case: str = Field(min_length=1, description="What the prompt is for")
    existing_prompt: str | None = Field(
        default=None, description="Current prompt to improve, if any"
    )


class OptimizeResponse(BaseModel):
    optimized_prompt: str
    use_case_profile: UseCaseProfile
    techniques: list[TechniqueVerdict] = Field(
        description="All 8 verdicts — applied and skipped, each with its why"
    )
    critic: CriticReport
    revised: bool = Field(
        description="True if the writer had to revise after critic feedback"
    )
    design_notes: str
    model: str
