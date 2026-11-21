from contextlib import asynccontextmanager
import sqlite3
from time import monotonic_ns

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .chat import Conversations
from .config import Settings
from .gateway import Gateway, ProvidersUnavailable
from .schemas import ChatRequest
from .storage import Store


class JsonCors(CORSMiddleware):
    def preflight_response(self, request_headers):
        response = super().preflight_response(request_headers)
        if response.status_code == 400:
            headers = {
                k: v
                for k, v in response.headers.items()
                if k not in ("content-length", "content-type")
            }
            return JSONResponse(
                {"detail": "CORS preflight rejected"}, status_code=400, headers=headers
            )
        return response


def create_app(settings=None, gateway=None):
    settings = settings or Settings.load()
    store = Store(settings.database)

    @asynccontextmanager
    async def lifespan(app):
        store.initialize()
        active = gateway or (
            Gateway(settings.model, settings.keys) if settings.keys else None
        )
        app.state.chat = Conversations(store, active, settings) if active else None
        yield

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def timed(request: Request, call_next):
        request.state.started = monotonic_ns()
        try:
            return await call_next(request)
        except Exception:
            return JSONResponse({"detail": "internal server error"}, status_code=500)

    app.add_middleware(
        JsonCors,
        allow_origins=list(settings.origins),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Simulate-Failure"],
    )

    @app.exception_handler(ProvidersUnavailable)
    async def exhausted(request, exc):
        return JSONResponse({"detail": "all providers unavailable"}, status_code=503)

    @app.get("/health")
    def health():
        if app.state.chat is None:
            raise HTTPException(503, "configure at least two distinct LLM_API_KEYS")
        try:
            store.check()
        except (sqlite3.Error, OSError):
            raise HTTPException(503, "database unavailable") from None
        return {
            "status": "ok",
            "keys_configured": len(settings.keys),
            "cache_enabled": True,
        }

    @app.post("/chat")
    async def chat(body: ChatRequest, request: Request):
        if app.state.chat is None:
            raise ProvidersUnavailable
        values = request.headers.getlist("X-Simulate-Failure")
        return await app.state.chat.send(
            body, ",".join(values) if values else None, request.state.started
        )

    @app.get("/sessions/{session_id:path}/messages")
    def history(session_id: str):
        saved = store.load(session_id)
        if saved is None:
            raise HTTPException(404, "session not found")
        return {"session_id": session_id, "messages": saved[1]}

    return app
