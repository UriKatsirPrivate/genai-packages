"""Chat stage and /chat endpoint tests (fake LLM, no API key)."""

from fastapi.testclient import TestClient

from app.config import Settings
from app.llm import LLMError
from app.main import create_app
from app.models import ChatRequest, ChatTurn, OptimizeRequest
from app.pipeline import PromptOptimizer

from tests.conftest import FakeLLM


def make_client(llm: FakeLLM) -> TestClient:
    app = create_app(optimizer=PromptOptimizer(llm, Settings()))
    return TestClient(app)


async def _result(optimizer):
    return await optimizer.optimize(OptimizeRequest(use_case="anything"))


async def test_chat_grounds_the_call_in_run_context(fake_llm, optimizer):
    result = await _result(optimizer)
    reply = await optimizer.chat(
        ChatRequest(
            use_case="anything",
            result=result,
            messages=[ChatTurn(role="user", content="why was 04 skipped?")],
        )
    )
    assert reply.reply == "fake chat reply"
    assert reply.updated_prompt is None

    _, _, user = fake_llm.calls_for("ChatReply")[-1]
    assert "CURRENT OPTIMIZED PROMPT" in user
    assert result.optimized_prompt in user
    assert "TECHNIQUE CATALOG" in user
    assert "CONVERSATION" in user
    assert "USER: why was 04 skipped?" in user


async def test_chat_history_is_forwarded_in_order(fake_llm, optimizer):
    result = await _result(optimizer)
    await optimizer.chat(
        ChatRequest(
            use_case="anything",
            result=result,
            messages=[
                ChatTurn(role="user", content="first question"),
                ChatTurn(role="assistant", content="first answer"),
                ChatTurn(role="user", content="second question"),
            ],
        )
    )
    _, _, user = fake_llm.calls_for("ChatReply")[-1]
    assert (
        user.index("USER: first question")
        < user.index("ASSISTANT: first answer")
        < user.index("USER: second question")
    )


def test_chat_endpoint_roundtrip_and_updated_prompt():
    llm = FakeLLM(chat_updated_prompt="REVISED PROMPT FROM CHAT")
    with make_client(llm) as client:
        result = client.post("/optimize", json={"use_case": "anything"}).json()
        resp = client.post(
            "/chat",
            json={
                "use_case": "anything",
                "result": result,
                "messages": [{"role": "user", "content": "make it shorter"}],
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "fake chat reply"
    assert body["updated_prompt"] == "REVISED PROMPT FROM CHAT"


def test_chat_endpoint_requires_messages():
    with make_client(FakeLLM()) as client:
        result = client.post("/optimize", json={"use_case": "anything"}).json()
        resp = client.post(
            "/chat", json={"use_case": "anything", "result": result, "messages": []}
        )
    assert resp.status_code == 422


def test_chat_endpoint_maps_llm_error_to_502():
    ok = FakeLLM()
    with make_client(ok) as client:
        result = client.post("/optimize", json={"use_case": "anything"}).json()
    with make_client(FakeLLM(error=LLMError("upstream exploded"))) as client:
        resp = client.post(
            "/chat",
            json={
                "use_case": "anything",
                "result": result,
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
    assert resp.status_code == 502
