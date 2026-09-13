"""Async Gemini wrapper: structured JSON output validated against Pydantic.

Auth is Vertex AI only (ADC / service identity), never GEMINI_API_KEY. The
genai.Client is created lazily on first use so the app stays importable
without GCP credentials; tests inject a fake client instead.
"""

import asyncio
import random
from typing import TypeVar

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

# RESOURCE_EXHAUSTED (429) and server-side errors are transient under Vertex AI
# quota pressure and worth retrying with backoff; other 4xx codes (bad request,
# auth) will not resolve on retry.
_RETRYABLE_CODES = {429, 500, 502, 503, 504}
_MAX_API_ATTEMPTS = 5
_BASE_DELAY_SECONDS = 1.0
_MAX_DELAY_SECONDS = 20.0


class LLMError(Exception):
    """Raised on SDK failures or unparseable model output."""


class LLM:
    def __init__(
        self,
        model: str,
        temperature: float = 0.2,
        client: genai.Client | None = None,
        max_concurrency: int = 5,
    ):
        self._model = model
        self._temperature = temperature
        self._client = client
        # Caps simultaneous in-flight Gemini calls for this LLM instance
        # (shared across requests), independent of how much the pipeline
        # fans out, to stay under Vertex AI's per-project rate quota.
        self._semaphore = asyncio.Semaphore(max_concurrency)

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(vertexai=True)
        return self._client

    async def _call_with_retry(
        self, *, user: str, config: types.GenerateContentConfig, label: str
    ):
        for attempt in range(_MAX_API_ATTEMPTS):
            try:
                async with self._semaphore:
                    return await self.client.aio.models.generate_content(
                        model=self._model,
                        contents=user,
                        config=config,
                    )
            except genai_errors.APIError as e:
                is_last_attempt = attempt == _MAX_API_ATTEMPTS - 1
                if e.code not in _RETRYABLE_CODES or is_last_attempt:
                    raise LLMError(f"Gemini call failed for {label}: {e}") from e
                delay = min(_BASE_DELAY_SECONDS * (2**attempt), _MAX_DELAY_SECONDS)
                await asyncio.sleep(delay + random.uniform(0, delay * 0.25))
            except Exception as e:
                raise LLMError(f"Gemini call failed for {label}: {e}") from e

    async def generate_structured(
        self, *, system: str, user: str, schema: type[T]
    ) -> T:
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=self._temperature,
        )
        last_error: Exception | None = None
        for _attempt in range(2):
            resp = await self._call_with_retry(
                user=user, config=config, label=schema.__name__
            )

            if isinstance(resp.parsed, schema):
                return resp.parsed

            text = resp.text
            if text is None:
                last_error = LLMError("response contained no text parts")
                continue
            try:
                return schema.model_validate_json(text)
            except ValidationError as e:
                last_error = e

        raise LLMError(
            f"Model output did not validate as {schema.__name__} "
            f"after retry: {last_error}"
        ) from last_error
