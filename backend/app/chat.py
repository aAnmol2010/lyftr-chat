import asyncio
from dataclasses import asdict
from time import monotonic_ns
from weakref import WeakValueDictionary

from fastapi import HTTPException

from .gateway import FAILURE_STATUSES


def parse_failures(header, count):
    if header is None:
        return {}
    aliases = [f"key_{index}" for index in range(1, count + 1)]
    failures = {}
    for item in header.split(","):
        alias, _, code = item.strip().partition("=")
        targets = aliases if alias == "*" else [alias]
        if code not in {str(status) for status in FAILURE_STATUSES} or any(
            target not in aliases or target in failures for target in targets
        ):
            raise HTTPException(422, "invalid X-Simulate-Failure")
        failures.update(dict.fromkeys(targets, int(code)))
    return failures


class Conversations:
    def __init__(self, store, gateway, settings):
        self.store = store
        self.gateway = gateway
        self.settings = settings
        self.locks = WeakValueDictionary()

    async def send(self, body, header, started):
        failures = (
            parse_failures(header, len(self.settings.keys))
            if self.settings.simulation
            else {}
        )
        sid = body.session_id
        lock = self.locks.setdefault(sid, asyncio.Lock())
        async with lock:
            stored = await asyncio.to_thread(
                self.store.load, sid, self.settings.history_turns
            )
            prompt, history = (
                stored if stored is not None else (self.settings.default_prompt, [])
            )
            if body.system_prompt is not None:
                prompt = body.system_prompt or self.settings.default_prompt
            elif not prompt.strip():
                prompt = self.settings.default_prompt
            messages = [{"role": "system", "content": prompt}]
            messages.extend(
                {"role": row["role"], "content": row["content"]} for row in history
            )
            messages.append({"role": "user", "content": body.message})
            result = await self.gateway.complete(messages, failures)
            metadata = asdict(result)
            reply = metadata.pop("reply")
            metadata["latency_ms"] = (monotonic_ns() - started) // 1_000_000
            write = asyncio.create_task(
                asyncio.to_thread(
                    self.store.commit_turn, sid, prompt, body.message, reply, metadata
                )
            )
            try:
                await asyncio.shield(write)
            except asyncio.CancelledError:
                # Keep this session locked until the off-thread transaction finishes.
                await write
                raise
            return {"session_id": sid, "reply": reply, "metadata": metadata}
