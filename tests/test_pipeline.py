"""Pipeline behavior tests, driven entirely by the deterministic FakeLLM."""

from app.config import Settings
from app.models import OptimizeRequest, UseCaseProfile
from app.pipeline import PromptOptimizer
from app.techniques import TECHNIQUES_BY_ID

from tests.conftest import FakeLLM

REQ = OptimizeRequest(
    use_case="Summarize legal contracts into risk bullet points",
    existing_prompt="Summarize this contract.",
)


async def test_all_eight_verdicts_present_and_sorted(optimizer):
    resp = await optimizer.optimize(REQ)
    ids = [v.technique_id for v in resp.techniques]
    assert ids == [f"{i:02d}" for i in range(1, 9)]


async def test_technique_ids_and_names_enforced_from_catalog(optimizer):
    resp = await optimizer.optimize(REQ)
    for v in resp.techniques:
        assert v.technique_id != "99"
        assert v.name == TECHNIQUES_BY_ID[v.technique_id].name
        assert v.name != "Wrong Name From Model"


async def test_irrelevant_verdicts_have_empty_application(optimizer):
    resp = await optimizer.optimize(REQ)
    irrelevant = [v for v in resp.techniques if not v.relevant]
    relevant = [v for v in resp.techniques if v.relevant]
    assert len(irrelevant) == 2
    assert all(v.application == "" for v in irrelevant)
    assert all(v.application for v in relevant)


async def test_no_revision_when_critic_approves(optimizer, fake_llm):
    resp = await optimizer.optimize(REQ)
    assert resp.revised is False
    assert resp.critic.approved is True
    assert len(fake_llm.calls_for("WriterOutput")) == 1


async def test_revision_loop_on_critic_rejection(settings):
    llm = FakeLLM(reject_critic_first_n=1)
    resp = await PromptOptimizer(llm, settings).optimize(REQ)
    assert resp.revised is True
    assert len(llm.calls_for("WriterOutput")) == 2
    assert len(llm.calls_for("CriticReport")) == 2
    assert resp.critic.approved is True


async def test_revision_bounded_by_settings():
    settings = Settings()
    assert settings.max_critic_revisions == 1
    llm = FakeLLM(reject_critic_first_n=5)
    resp = await PromptOptimizer(llm, settings).optimize(REQ)
    assert len(llm.calls_for("WriterOutput")) == 2
    assert resp.revised is True
    assert resp.critic.approved is False


async def test_response_shape(optimizer, settings):
    resp = await optimizer.optimize(REQ)
    assert isinstance(resp.optimized_prompt, str)
    assert resp.optimized_prompt
    assert resp.model == settings.model
    assert isinstance(resp.use_case_profile, UseCaseProfile)
    assert resp.design_notes
