"""Run the public API contract against a configured stack. Uses real inference on live hosts."""

import json
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


def verify(base):
    def request(path, body=None, failure=None, expected=200):
        headers = {"Content-Type": "application/json"}
        if failure:
            headers["X-Simulate-Failure"] = failure
        req = Request(
            base.rstrip("/") + path,
            json.dumps(body).encode() if body is not None else None,
            headers,
        )
        try:
            response = urlopen(req, timeout=90)
        except HTTPError as exc:
            response = exc
        with response:
            result = json.load(response)
            if response.status != expected:
                raise RuntimeError(
                    f"{path}: HTTP {response.status}, expected {expected}"
                )
            return result

    sid = uuid4().hex
    prompt = f"Reply with one short greeting. Reference {sid}."

    def send(session, text, header=None, expected=200):
        return request(
            "/chat", {"session_id": session, "message": text}, header, expected
        )

    health = request("/health")
    assert (
        health["status"] == "ok"
        and health["keys_configured"] >= 2
        and health["cache_enabled"] is True
    )
    live = send(sid, prompt)
    cached = send(sid + "-repeat", prompt)
    m, c = live["metadata"], cached["metadata"]
    assert (
        m["resolution_source"] == "LIVE_INFERENCE"
        and c["resolution_source"] == "LLM_CACHE"
    )
    assert (
        c["latency_ms"] < m["latency_ms"]
        and c["key_id"] is None
        and c["fallback_attempts"] == 0
    )
    assert live["reply"].strip() and live["reply"] == cached["reply"]
    assert all(c[k] == m[k] for k in ("input_tokens", "output_tokens", "model"))
    for status in (429, 500):
        fallback = send(sid, "Continue briefly.", f"key_1={status}")
        meta = fallback["metadata"]
        assert fallback["reply"].strip() and (
            meta["resolution_source"],
            meta["key_id"],
            meta["fallback_attempts"],
        ) == ("LIVE_INFERENCE", "key_2", 1)
    path = f"/sessions/{sid}/messages"
    history = request(path)
    assert [x["role"] for x in history["messages"]] == ["user", "assistant"] * 3
    assert history["messages"][1]["metadata"] == m
    assert send(sid, "exhaust", "*=429", 503) == {"detail": "all providers unavailable"}
    assert "detail" in send(sid, "   ", expected=422)
    assert request(path) == history
    assert request(path.replace(sid, sid + "-unknown"), expected=404) == {
        "detail": "session not found"
    }
    print(
        f"Passed health, live, cache, failover, usage, history and errors. Persistence session: {sid}"
    )
    return sid


if __name__ == "__main__":
    verify(sys.argv[1])
