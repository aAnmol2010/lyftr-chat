import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

MESSAGES = [
    {"role": "system", "content": "Be concise."},
    {"role": "user", "content": "Hello"},
]


@pytest.fixture
def provider():
    calls = []
    errors = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            key = (
                self.headers.get("x-goog-api-key")
                or parse_qs(urlparse(self.path).query).get("key", [""])[0]
            )
            calls.append((key, body))
            status = errors.get(key, 200)
            time.sleep(0.05)
            payload = {
                "candidates": [
                    {
                        "content": {
                            "role": "model",
                            "parts": [{"text": "Hello there."}],
                        },
                        "finishReason": "STOP",
                        "index": 0,
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 19,
                    "candidatesTokenCount": 7,
                    "totalTokenCount": 26,
                },
                "modelVersion": "gemini-2.5-flash-lite",
            }
            if "modelVersion" in errors:
                payload["modelVersion"] = errors["modelVersion"]
            if "usageMetadata" in errors:
                payload["usageMetadata"] = errors["usageMetadata"]
            if status != 200:
                payload = {
                    "error": {
                        "code": status,
                        "message": "quota exhausted"
                        if status == 429
                        else "temporarily unavailable",
                        "status": "RESOURCE_EXHAUSTED" if status == 429 else "INTERNAL",
                    }
                }
            encoded = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", calls, errors
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.fixture
def gateway(provider):
    from app.gateway import Gateway

    return Gateway(
        "gemini/gemini-2.5-flash-lite",
        ("test-first", "test-second"),
        api_base=provider[0],
    )


@pytest.mark.parametrize("status", [429, 500, 502, 503])
async def test_provider_failover_then_cache(gateway, provider, status):
    _, calls, errors = provider
    errors["test-first"] = status
    live = await gateway.complete(MESSAGES, {})
    assert [call[0] for call in calls] == ["test-first", "test-second"]
    assert (live.key_id, live.fallback_attempts, live.resolution_source) == (
        "key_2",
        1,
        "LIVE_INFERENCE",
    )
    hit = await gateway.complete(MESSAGES, {})
    assert len(calls) == 2
    assert (hit.reply, hit.input_tokens, hit.output_tokens) == (live.reply, 19, 7)
    assert (hit.key_id, hit.fallback_attempts, hit.resolution_source) == (
        None,
        0,
        "LLM_CACHE",
    )


async def test_simulation_isolated_from_cache_and_next_request(gateway, provider):
    from app.gateway import ProvidersUnavailable

    await gateway.complete(MESSAGES, {})
    with pytest.raises(ProvidersUnavailable):
        await gateway.complete(MESSAGES, {"key_1": 429, "key_2": 500})
    result = await gateway.complete(MESSAGES, {"key_1": 500})
    assert (result.key_id, result.fallback_attempts) == ("key_2", 1)
    changed = MESSAGES + [
        {"role": "assistant", "content": "Hi"},
        {"role": "user", "content": "Again"},
    ]
    assert (await gateway.complete(changed, {})).key_id == "key_1"
    assert [c[0] for c in provider[1]] == ["test-first", "test-second", "test-first"]


async def test_change_in_prompt_message_or_history_misses(gateway, provider):
    historic = MESSAGES + [
        {"role": "assistant", "content": "Hello there."},
        {"role": "user", "content": "Hello"},
    ]
    for messages in [
        MESSAGES,
        [{**MESSAGES[0], "content": "Use French"}, MESSAGES[1]],
        [MESSAGES[0], {**MESSAGES[1], "content": "Another"}],
        historic,
    ]:
        result = await gateway.complete(messages, {})
        assert result.resolution_source == "LIVE_INFERENCE"
    assert len(provider[1]) == 4
    assert (
        gateway.cache.get_cache(model="gemini/another-model", messages=MESSAGES) is None
    )


async def test_all_real_providers_fail(gateway, provider):
    from app.gateway import ProvidersUnavailable

    provider[2].update({"test-first": 503, "test-second": 429})
    with pytest.raises(ProvidersUnavailable):
        await gateway.complete(MESSAGES, {})
    assert [c[0] for c in provider[1]] == ["test-first", "test-second"]


async def test_served_model_version_survives_cache(gateway, provider):
    provider[2]["modelVersion"] = "gemini-resolved-version"
    for source in ("LIVE_INFERENCE", "LLM_CACHE"):
        result = await gateway.complete(MESSAGES, {})
        assert result.resolution_source == source
        assert result.model == "gemini/gemini-resolved-version"


@pytest.mark.parametrize(
    "usage", [{}, {"promptTokenCount": 19}, {"candidatesTokenCount": 7}]
)
async def test_partial_usage_rejected_and_never_cached(gateway, provider, usage):
    from app.gateway import ProvidersUnavailable

    provider[2]["usageMetadata"] = usage
    with pytest.raises(ProvidersUnavailable):
        await gateway.complete(MESSAGES, {})
    del provider[2]["usageMetadata"]
    assert (await gateway.complete(MESSAGES, {})).resolution_source == "LIVE_INFERENCE"


async def test_safe_failure_log_and_served_model_prefix(gateway, monkeypatch, caplog):
    from types import SimpleNamespace
    from app.gateway import ProvidersUnavailable

    class UpstreamError(Exception):
        status_code = 404

    async def bad(**kwargs):
        raise UpstreamError("private credential or prompt")

    monkeypatch.setattr(gateway.router, "acompletion", bad)
    with pytest.raises(ProvidersUnavailable):
        await gateway.complete(MESSAGES, {})
    record = next(r for r in caplog.records if r.name == "app.gateway")
    assert record.getMessage() == "provider failure: UpstreamError status=404"
    assert record.exc_info is None

    async def ok(**kwargs):
        return SimpleNamespace(
            model="served-model",
            _hidden_params={"model_id": "key_1"},
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
            usage=SimpleNamespace(prompt_tokens=7, completion_tokens=1),
        )

    gateway.model = "other/configured-model"
    monkeypatch.setattr(gateway.router, "acompletion", ok)
    assert (await gateway.complete(MESSAGES, {})).model == "other/served-model"
