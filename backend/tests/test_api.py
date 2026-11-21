import asyncio

import httpx
import pytest


@pytest.fixture
async def api(tmp_path):
    from app.config import Settings
    from app.gateway import Completion, ProvidersUnavailable
    from app.main import create_app

    settings = Settings(
        ("a", "b"), tmp_path / "history.db", ("http://localhost:3000",), True
    )
    calls = []

    class Echo:
        async def complete(self, messages, failures):
            calls.append(messages)
            await asyncio.sleep(0.015)
            if failures:
                raise ProvidersUnavailable
            return Completion(
                "Reply", "gemini/test", len(messages), 7, "LIVE_INFERENCE", "key_1", 0
            )

    app = create_app(settings, Echo())
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client, calls


async def test_health_and_missing_history(api):
    client, _ = api
    assert (await client.get("/health")).json() == {
        "status": "ok",
        "keys_configured": 2,
        "cache_enabled": True,
    }
    assert (await client.get("/sessions/unknown/messages")).json() == {
        "detail": "session not found"
    }
    assert (await client.get("/docs")).status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"session_id": "", "message": "a"},
        {"session_id": "a", "message": "   "},
        {"session_id": "a" * 129, "message": "a"},
        {"session_id": "a", "message": "a" * 4001},
    ],
)
async def test_invalid_never_writes(api, payload):
    client, calls = api
    res = await client.post("/chat", json=payload)
    assert res.status_code == 422 and "detail" in res.json()
    assert not calls
    assert (await client.get("/sessions/a/messages")).status_code == 404


async def test_atomic_turns_and_prompt_override(api):
    client, calls = api

    async def send(message, **kwargs):
        return await client.post(
            "/chat", json={"session_id": "s", "message": message, **kwargs}
        )

    first = await send(" hello ", system_prompt="Be brief")
    assert first.status_code == 200
    before = (await client.get("/sessions/s/messages")).json()
    failed = await client.post(
        "/chat",
        json={"session_id": "s", "message": "bad", "system_prompt": "wrong"},
        headers={"X-Simulate-Failure": "*=429"},
    )
    assert (failed.status_code, failed.json()) == (
        503,
        {"detail": "all providers unavailable"},
    )
    assert (await client.get("/sessions/s/messages")).json() == before
    await asyncio.gather(send("next"), send("last"))
    assert [len(messages) for messages in calls] == [2, 4, 4, 6]
    assert calls[-1][0]["content"] == "Be brief"
    history = (await client.get("/sessions/s/messages")).json()["messages"]
    assert len(history) == 6 and history[0] == {"role": "user", "content": "hello"}
    assert history[1]["metadata"] == first.json()["metadata"]


async def test_malformed_json_and_header(api):
    client, calls = api
    assert (
        await client.post(
            "/chat", content="{", headers={"content-type": "application/json"}
        )
    ).status_code == 422
    assert (
        await client.post(
            "/chat",
            json={"session_id": "s", "message": "hello"},
            headers={"X-Simulate-Failure": "key_1=401"},
        )
    ).status_code == 422
    assert not calls


async def test_without_keys_history_available_and_readiness_false(
    tmp_path, monkeypatch
):
    from app.main import create_app

    monkeypatch.delenv("LLM_API_KEYS", raising=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/app.db")
    app = create_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            assert (await client.get("/health")).status_code == 503
            response = await client.post(
                "/chat", json={"session_id": "a", "message": "hi"}
            )
            assert (response.status_code, response.json()) == (
                503,
                {"detail": "all providers unavailable"},
            )
            assert (await client.get("/sessions/a/messages")).status_code == 404


async def test_inclusive_valid_boundaries(api):
    client, _ = api
    for sid, text in (("a", "x"), ("z" * 128, " " + "y" * 4000 + " ")):
        response = await client.post("/chat", json={"session_id": sid, "message": text})
        assert response.status_code == 200
        history = await client.get(f"/sessions/{sid}/messages")
        assert history.json()["messages"][0]["content"] == text.strip()


def test_simulation_disabled_preserves_normal_chat(tmp_path):
    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.gateway import Completion
    from app.main import create_app

    class Healthy:
        async def complete(self, messages, failures):
            assert failures == {}
            return Completion("Yes", "gemini/test", 13, 2, "LIVE_INFERENCE", "key_1", 0)

    settings = Settings(("a", "b"), tmp_path / "disabled.db", (), False)
    with TestClient(create_app(settings, Healthy())) as client:
        r = client.post(
            "/chat",
            json={"session_id": "a", "message": "Hi"},
            headers={"X-Simulate-Failure": "*=429"},
        )
        assert r.status_code == 200
        assert r.json()["metadata"]["key_id"] == "key_1"


async def test_repeated_failure_header_parsed_together(api):
    client, calls = api
    res = await client.post(
        "/chat",
        json={"session_id": "s", "message": "hello"},
        headers=[
            ("X-Simulate-Failure", "key_1=429"),
            ("X-Simulate-Failure", "key_1=500"),
        ],
    )
    assert res.status_code == 422
    assert not calls


async def test_disallowed_preflight_json(api):
    client, _ = api
    res = await client.options(
        "/chat",
        headers={
            "Origin": "https://unlisted.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert res.status_code == 400 and res.json()["detail"]


async def test_allowed_preflight_includes_failure_header(api):
    client, _ = api
    res = await client.options(
        "/chat",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-simulate-failure",
        },
    )
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "x-simulate-failure" in res.headers["access-control-allow-headers"].lower()


async def test_prompt_reset_and_cap(api):
    client, calls = api
    for prompt in ["  brief  ", " ", None]:
        data = {"session_id": "s", "message": "hi"}
        if prompt is not None:
            data["system_prompt"] = prompt
        assert (await client.post("/chat", json=data)).status_code == 200
    from app.config import Settings

    assert [c[0]["content"] for c in calls] == [
        "brief",
        Settings.default_prompt,
        Settings.default_prompt,
    ]
    assert (
        await client.post("/chat", json={**data, "system_prompt": "x" * 4001})
    ).status_code == 422


async def test_context_window_preserves_full_history(api):
    client, calls = api
    for i in range(23):
        await client.post("/chat", json={"session_id": "long", "message": str(i)})
    assert len(calls[-1]) == 42
    assert calls[-1][1]["content"] == "2"
    assert len((await client.get("/sessions/long/messages")).json()["messages"]) == 46


async def test_storage_error_cors_and_readiness(tmp_path, monkeypatch):
    from app.config import Settings
    from app.main import create_app
    from app.storage import Store
    import sqlite3

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/err.db")
    monkeypatch.setenv("ALLOWED_ORIGINS", " http://localhost:3101/ ")
    monkeypatch.setenv("LLM_API_KEYS", "a,b")
    app = create_app(Settings.load(), object())

    def broken(*args):
        raise sqlite3.OperationalError("private diagnostic")

    monkeypatch.setattr(Store, "check", broken)
    monkeypatch.setattr(Store, "load", broken)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as c:
            for path, code in [("/health", 503), ("/sessions/s/messages", 500)]:
                res = await c.get(path, headers={"Origin": "http://localhost:3101"})
                assert res.status_code == code
                assert (
                    res.headers["access-control-allow-origin"]
                    == "http://localhost:3101"
                )
                assert "private diagnostic" not in res.text and "detail" in res.json()
