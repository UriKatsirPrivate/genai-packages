"""Unit tests for the LLM client wrapper, independent of FakeLLM.

FakeLLM (used everywhere else) duck-types around app.llm.LLM entirely, so
none of these behaviors — lazy Vertex AI client construction, the resp.parsed
fast path, the resp.text JSON fallback, the retry-on-validation-failure loop,
and SDK exception wrapping — were exercised anywhere else.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from google.genai import errors as genai_errors

from app.llm import LLM, LLMError
from app.models import ChatReply


def _api_error(code: int) -> genai_errors.APIError:
    """Build a real APIError/ClientError/ServerError, as the SDK would raise."""
    details = {"error": {"code": code, "message": "boom", "status": "ERROR"}}
    try:
        genai_errors.APIError.raise_error(code, details, None)
    except genai_errors.APIError as e:
        return e
    raise AssertionError("raise_error did not raise")



def _resp(parsed=None, text=None):
    return MagicMock(parsed=parsed, text=text)


def _client_returning(*responses_or_error):
    """A fake genai.Client whose aio.models.generate_content yields the given
    responses in order, or raises if given a single exception."""
    side_effect = responses_or_error[0] if (
        len(responses_or_error) == 1 and isinstance(responses_or_error[0], Exception)
    ) else list(responses_or_error)
    call = AsyncMock(side_effect=side_effect)
    client = MagicMock()
    client.aio.models.generate_content = call
    return client, call


def test_client_is_constructed_lazily_with_vertexai_and_cached(monkeypatch):
    ctor = MagicMock(return_value=MagicMock())
    monkeypatch.setattr("app.llm.genai.Client", ctor)

    llm = LLM(model="gemini-3.8-flash")
    ctor.assert_not_called()

    first = llm.client
    second = llm.client

    ctor.assert_called_once_with(vertexai=True)
    assert first is second


async def test_generate_structured_returns_resp_parsed_directly():
    reply = ChatReply(reply="hi")
    client, call = _client_returning(_resp(parsed=reply))
    llm = LLM(model="m", client=client)

    result = await llm.generate_structured(system="sys", user="usr", schema=ChatReply)

    assert result is reply
    call.assert_awaited_once()
    assert call.await_args.kwargs["model"] == "m"
    assert call.await_args.kwargs["contents"] == "usr"


async def test_generate_structured_falls_back_to_parsing_resp_text():
    text = json.dumps({"reply": "from text"})
    client, call = _client_returning(_resp(parsed=None, text=text))
    llm = LLM(model="m", client=client)

    result = await llm.generate_structured(system="sys", user="usr", schema=ChatReply)

    assert result == ChatReply(reply="from text")
    call.assert_awaited_once()


async def test_generate_structured_retries_once_then_succeeds():
    bad = _resp(parsed=None, text="not valid json")
    good = _resp(parsed=None, text=json.dumps({"reply": "ok"}))
    client, call = _client_returning(bad, good)
    llm = LLM(model="m", client=client)

    result = await llm.generate_structured(system="sys", user="usr", schema=ChatReply)

    assert result == ChatReply(reply="ok")
    assert call.await_count == 2


async def test_generate_structured_raises_llm_error_after_exhausting_retries():
    always_bad = _resp(parsed=None, text=None)
    client, call = _client_returning(always_bad, always_bad)
    llm = LLM(model="m", client=client)

    with pytest.raises(LLMError):
        await llm.generate_structured(system="sys", user="usr", schema=ChatReply)

    assert call.await_count == 2


async def test_generate_structured_wraps_sdk_exception_in_llm_error():
    client, _ = _client_returning(RuntimeError("upstream exploded"))
    llm = LLM(model="m", client=client)

    with pytest.raises(LLMError, match="upstream exploded"):
        await llm.generate_structured(system="sys", user="usr", schema=ChatReply)


async def test_generate_structured_does_not_retry_after_sdk_exception():
    client, call = _client_returning(RuntimeError("boom"))
    llm = LLM(model="m", client=client)

    with pytest.raises(LLMError):
        await llm.generate_structured(system="sys", user="usr", schema=ChatReply)

    call.assert_awaited_once()


async def test_generate_structured_retries_with_backoff_on_429(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr("app.llm.asyncio.sleep", sleep)
    reply = ChatReply(reply="hi")
    client, call = _client_returning(_api_error(429), _resp(parsed=reply))
    llm = LLM(model="m", client=client)

    result = await llm.generate_structured(system="sys", user="usr", schema=ChatReply)

    assert result is reply
    assert call.await_count == 2
    sleep.assert_awaited_once()


async def test_generate_structured_raises_after_exhausting_api_retries(monkeypatch):
    monkeypatch.setattr("app.llm.asyncio.sleep", AsyncMock())
    client, call = _client_returning(_api_error(429))
    llm = LLM(model="m", client=client)

    with pytest.raises(LLMError, match="ChatReply"):
        await llm.generate_structured(system="sys", user="usr", schema=ChatReply)

    assert call.await_count == 5


async def test_generate_structured_does_not_retry_non_retryable_api_error(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr("app.llm.asyncio.sleep", sleep)
    client, call = _client_returning(_api_error(400))
    llm = LLM(model="m", client=client)

    with pytest.raises(LLMError):
        await llm.generate_structured(system="sys", user="usr", schema=ChatReply)

    call.assert_awaited_once()
    sleep.assert_not_awaited()


async def test_max_concurrency_limits_simultaneous_calls():
    in_flight = 0
    peak = 0

    async def slow_generate_content(**_kwargs):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0)
        in_flight -= 1
        return _resp(parsed=ChatReply(reply="hi"))

    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(side_effect=slow_generate_content)
    llm = LLM(model="m", client=client, max_concurrency=2)

    await asyncio.gather(
        *(
            llm.generate_structured(system="sys", user="usr", schema=ChatReply)
            for _ in range(5)
        )
    )

    assert peak <= 2
