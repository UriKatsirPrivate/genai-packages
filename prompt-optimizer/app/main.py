"""FastAPI layer over the PromptOptimizer pipeline.

The optimizer is built lazily inside the lifespan (never at import time), so
importing this module requires no API key; tests inject a ready-made
optimizer into create_app() instead.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

STATIC_DIR = Path(__file__).parent / "static"

from app.config import get_settings
from app.llm import LLM, LLMError
from app.models import ChatReply, ChatRequest, OptimizeRequest, OptimizeResponse
from app.pipeline import PromptOptimizer


def create_app(optimizer: PromptOptimizer | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if optimizer is not None:
            app.state.optimizer = optimizer
            app.state.model = optimizer.settings.model
        else:
            settings = get_settings()
            llm = LLM(model=settings.model, temperature=settings.temperature)
            app.state.optimizer = PromptOptimizer(llm, settings)
            app.state.model = settings.model
        yield

    app = FastAPI(
        title="Prompt Optimizer",
        description=(
            "Multi-agent prompt optimization service built on the eight "
            "techniques from the talk 'How LLMs Actually Work — Prompting "
            "from First Principles': a use-case analyzer, eight parallel "
            "technique judges, a prompt writer, and a critic."
        ),
        lifespan=lifespan,
    )

    @app.post("/optimize", response_model=OptimizeResponse)
    async def optimize(req: OptimizeRequest) -> OptimizeResponse:
        try:
            return await app.state.optimizer.optimize(req)
        except LLMError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/optimize/stream")
    async def optimize_stream(req: OptimizeRequest) -> StreamingResponse:
        """NDJSON stream: one progress event per line, then a final
        {"event": "result"} (or {"event": "error"}) line."""
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        async def progress(event: dict[str, Any]) -> None:
            await queue.put(event)

        async def run() -> None:
            try:
                result = await app.state.optimizer.optimize(req, progress=progress)
                await queue.put({"event": "result", "data": result.model_dump()})
            except LLMError as exc:
                await queue.put({"event": "error", "detail": str(exc)})
            except Exception as exc:
                await queue.put({"event": "error", "detail": f"internal error: {exc}"})
            finally:
                await queue.put(None)

        async def lines() -> AsyncIterator[str]:
            task = asyncio.create_task(run())
            try:
                while (event := await queue.get()) is not None:
                    yield json.dumps(event) + "\n"
                await task
            finally:
                task.cancel()

        return StreamingResponse(lines(), media_type="application/x-ndjson")

    @app.post("/chat", response_model=ChatReply)
    async def chat(req: ChatRequest) -> ChatReply:
        try:
            return await app.state.optimizer.chat(req)
        except LLMError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "model": app.state.model}

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
