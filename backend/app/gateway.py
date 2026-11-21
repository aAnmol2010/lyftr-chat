import asyncio
import logging
import os
from dataclasses import dataclass

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
import litellm
from litellm.caching.caching import Cache
from litellm import Router

# Provider diagnostics can contain request headers or conversation text.
for logger in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy", "httpx"):
    logging.getLogger(logger).setLevel(logging.CRITICAL)
litellm.suppress_debug_info = True

FAILURE_STATUSES = (429, 500, 502, 503)


class SimulatedFailure(Exception):
    def __init__(self, status_code: int):
        super().__init__(status_code)
        self.status_code = status_code


class ProvidersUnavailable(Exception):
    pass


@dataclass(frozen=True)
class Completion:
    reply: str
    model: str
    input_tokens: int
    output_tokens: int
    resolution_source: str
    key_id: str | None
    fallback_attempts: int


class Gateway:
    def __init__(self, model: str, keys: tuple[str, ...], *, api_base=None):
        self.model = model
        self.aliases = tuple(f"key_{i}" for i in range(1, len(keys) + 1))
        self.cache = Cache(type="local", default_in_memory_ttl=600)
        deployments = []
        for alias, key in zip(self.aliases, keys, strict=True):
            params = {"model": model, "api_key": key, "max_retries": 0}
            if api_base:
                params["api_base"] = api_base
            deployments.append(self._deployment(alias, params))
            # Dedicated error deployments never share health or mutable settings with live keys.
            for status in FAILURE_STATUSES:
                failure = SimulatedFailure(status)
                deployments.append(
                    self._deployment(
                        f"{alias}_{status}", {**params, "mock_response": failure}
                    )
                )
        self.router = Router(
            model_list=deployments,
            num_retries=0,
            timeout=15,
            max_fallbacks=len(keys) - 1,
            disable_cooldowns=True,
        )

    @staticmethod
    def _deployment(name, params):
        return {
            "model_name": name,
            "litellm_params": params,
            "model_info": {"id": name},
        }

    async def complete(
        self, messages: list[dict[str, str]], failures: dict[str, int]
    ) -> Completion:
        identity = {"model": self.model, "messages": messages}
        if not failures:
            cached = self.cache.get_cache(**identity)
            if cached is not None:
                return Completion(
                    **cached,
                    resolution_source="LLM_CACHE",
                    key_id=None,
                    fallback_attempts=0,
                )

        route = [
            f"{alias}_{failures[alias]}" if alias in failures else alias
            for alias in self.aliases
        ]
        try:
            async with asyncio.timeout(15 * len(route) + 2):
                result = await self.router.acompletion(
                    model=route[0],
                    messages=messages,
                    fallbacks=[{route[0]: route[1:]}],
                    caching=False,
                    max_retries=0,
                )
            answered = result._hidden_params["model_id"]
            text = result.choices[0].message.content
            if (
                answered not in self.aliases
                or not isinstance(text, str)
                or not text.strip()
            ):
                raise ProvidersUnavailable
            usage = result.usage
            served = result.model or self.model
            if "/" not in served and "/" in self.model:
                served = self.model.partition("/")[0] + "/" + served
            payload = dict(
                reply=text,
                model=served,
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
            )
            if any(
                type(value) is not int or value <= 0
                for value in (usage.prompt_tokens, usage.completion_tokens)
            ):
                raise ProvidersUnavailable
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            logging.getLogger(__name__).warning(
                "provider failure: %s status=%s",
                type(exc).__name__,
                status if type(status) is int else None,
            )
            raise ProvidersUnavailable from None
        if not failures:
            self.cache.add_cache(payload, **identity)
        return Completion(
            **payload,
            resolution_source="LIVE_INFERENCE",
            key_id=answered,
            fallback_attempts=self.aliases.index(answered),
        )
