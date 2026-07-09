"""Progress-event and /optimize/stream tests (fake LLM, no API key)."""

import json

from fastapi.testclient import TestClient

from app.config import Settings
from app.llm import LLMError
from app.main import create_app
from app.models import OptimizeRequest
from app.pipeline import PromptOptimizer

from tests.conftest import FakeLLM


def make_client(llm: FakeLLM) -> TestClient:
    app = create_app(optimizer=PromptOptimizer(llm, Settings()))
    return TestClient(app)


async def test_pipeline_emits_progress_events(optimizer):
    events = []

    async def progress(event):
        events.append(event)

    await optimizer.optimize(OptimizeRequest(use_case="anything"), progress=progress)

    stages = [
        (e["stage"], e["status"]) for e in events if e["event"] == "stage"
    ]
    assert ("analyzer", "running") in stages and ("analyzer", "done") in stages
    assert ("judges", "running") in stages and ("judges", "done") in stages
    assert ("writer", "done") in stages and ("critic", "done") in stages

    judge_events = [e for e in events if e["event"] == "judge_done"]
    assert len(judge_events) == 8
    assert {e["technique_id"] for e in judge_events} == {
        f"{i:02d}" for i in range(1, 9)
    }
    assert [e["done"] for e in judge_events] == list(range(1, 9))

    # ordering: analyzer done before any judge, all judges before writer
    kinds = [
        (e["event"], e.get("stage"), e.get("status")) for e in events
    ]
    assert kinds.index(("stage", "analyzer", "done")) < kinds.index(
        ("judge_done", None, None)
    )
    assert kinds.index(("stage", "writer", "running")) > max(
        i for i, k in enumerate(kinds) if k[0] == "judge_done"
    )


async def test_revision_emits_second_writer_and_critic_rounds(fake_llm, settings):
    fake_llm.reject_critic_first_n = 1
    events = []

    async def progress(event):
        events.append(event)

    optimizer = PromptOptimizer(fake_llm, settings)
    await optimizer.optimize(OptimizeRequest(use_case="anything"), progress=progress)

    writer_drafts = [
        e["draft"]
        for e in events
        if e["event"] == "stage" and e["stage"] == "writer" and e["status"] == "done"
    ]
    critic_rounds = [
        (e["round"], e["approved"])
        for e in events
        if e["event"] == "stage" and e["stage"] == "critic" and e["status"] == "done"
    ]
    assert writer_drafts == [1, 2]
    assert critic_rounds == [(1, False), (2, True)]


async def test_optimize_without_progress_callback_still_works(optimizer):
    resp = await optimizer.optimize(OptimizeRequest(use_case="anything"))
    assert resp.optimized_prompt


def test_stream_endpoint_events_then_result():
    with make_client(FakeLLM()) as client:
        resp = client.post("/optimize/stream", json={"use_case": "anything"})
    assert resp.status_code == 200
    lines = [json.loads(line) for line in resp.text.strip().splitlines()]
    assert sum(1 for e in lines if e["event"] == "judge_done") == 8
    assert lines[-1]["event"] == "result"
    assert lines[-1]["data"]["optimized_prompt"]
    assert len(lines[-1]["data"]["techniques"]) == 8


def test_stream_endpoint_error_event():
    with make_client(FakeLLM(error=LLMError("upstream exploded"))) as client:
        resp = client.post("/optimize/stream", json={"use_case": "anything"})
    assert resp.status_code == 200
    lines = [json.loads(line) for line in resp.text.strip().splitlines()]
    assert lines[-1]["event"] == "error"
    assert "upstream exploded" in lines[-1]["detail"]
