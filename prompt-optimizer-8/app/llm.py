"""Async Gemini wrapper: structured JSON output validated against Pydantic.

The genai.Client is created lazily on first use so the app stays importable
without a GEMINI_API_KEY; tests inject a fake client instead.
"""

from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Raised on SDK failures or unparseable model output."""


class LLM:
    def __init__(
        self,
        model: str,
        temperature: float = 0.2,
        client: genai.Client | None = None,
    ):
        self._model = model
        self._temperature = temperature
        self._client = client

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client()
        return self._client

    async def generate_structured(
        self, *, system: str, user: str, schema: type[T]
    ) -> T:
        last_error: Exception | None = None
        for _attempt in range(2):
            try:
                resp = await self.client.aio.models.generate_content(
                    model=self._model,
                    contents=user,
                    config=types.GenerateContentConfig(
                        system_instruction=system,
                        response_mime_type="application/json",
                        response_schema=schema,
                        temperature=self._temperature,
                    ),
                )
            except Exception as e:
                raise LLMError(
                    f"Gemini call failed for {schema.__name__}: {e}"
                ) from e

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
