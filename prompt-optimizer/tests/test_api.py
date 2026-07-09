"""API layer tests via fastapi.testclient (context-manager form runs lifespan)."""

from fastapi.testclient import TestClient

from app.config import Settings
from app.llm import LLMError
from app.main import create_app
from app.pipeline import PromptOptimizer

from tests.conftest import FakeLLM


def make_client(llm: FakeLLM) -> TestClient:
    app = create_app(optimizer=PromptOptimizer(llm, Settings()))
    return TestClient(app)


def test_optimize_200_shape():
    with make_client(FakeLLM()) as client:
        resp = client.post(
            "/optimize",
            json={
                "use_case": "Summarize legal contracts into risk bullet points",
                "existing_prompt": "Summarize this contract.",
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["optimized_prompt"]
    assert len(body["techniques"]) == 8
    assert "approved" in body["critic"]
    assert "checks" in body["critic"]


def test_optimize_missing_use_case_422():
    with make_client(FakeLLM()) as client:
        resp = client.post("/optimize", json={"existing_prompt": "x"})
    assert resp.status_code == 422


def test_llm_error_maps_to_502():
    with make_client(FakeLLM(error=LLMError("upstream exploded"))) as client:
        resp = client.post("/optimize", json={"use_case": "anything at all"})
    assert resp.status_code == 502


def test_healthz():
    with make_client(FakeLLM()) as client:
        resp = client.get("/healthz")
    assert resp.status_code == 200


def test_index_serves_web_ui():
    with make_client(FakeLLM()) as client:
        resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "Prompt Optimizer" in resp.text
