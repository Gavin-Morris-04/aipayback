"""The only place in AIPayback that talks to the Claude API.

Every call: cache lookup -> (offline? stop) -> prompt-size check -> run reservation check
-> API call -> exact cost from usage -> ledger line -> cached output.

The SDK client is always built with api_key=AIPAYBACK_API_KEY passed explicitly. If that
key is missing we raise instead of letting the SDK fall back to ANTHROPIC_API_KEY or a
login profile.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from aipb.budget.estimator import Estimator
from aipb.budget.guard import BudgetGuard, Run
from aipb.budget.ledger import CallRecord, utc_now
from aipb.budget.pricing import TokenUsage
from aipb.llm.cache import CacheKey, OutputCache, input_hash


class OfflineCacheMiss(RuntimeError):
    pass


class MissingApiKey(RuntimeError):
    pass


SdkFactory = Callable[[str], Any]


def default_sdk_factory(api_key: str) -> Any:
    import anthropic

    return anthropic.Anthropic(api_key=api_key, max_retries=3)


def usage_from_sdk(usage: Any) -> tuple[TokenUsage, int]:
    """Convert the SDK's usage object into TokenUsage (+ thinking tokens, for reporting)."""
    cache_5m = cache_1h = 0
    breakdown = getattr(usage, "cache_creation", None)
    if breakdown is not None:
        cache_5m = getattr(breakdown, "ephemeral_5m_input_tokens", 0) or 0
        cache_1h = getattr(breakdown, "ephemeral_1h_input_tokens", 0) or 0
    else:
        cache_5m = getattr(usage, "cache_creation_input_tokens", 0) or 0
    details = getattr(usage, "output_tokens_details", None)
    thinking = (getattr(details, "thinking_tokens", 0) or 0) if details is not None else 0
    return (
        TokenUsage(
            input_tokens=usage.input_tokens or 0,
            output_tokens=usage.output_tokens or 0,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            cache_write_5m_tokens=cache_5m,
            cache_write_1h_tokens=cache_1h,
        ),
        thinking,
    )


@dataclass(frozen=True)
class LLMResult:
    response: dict
    cached: bool
    call_id: str | None
    cost_usd: Decimal

    @property
    def stop_reason(self) -> str | None:
        return self.response.get("stop_reason")

    def text(self) -> str:
        return "".join(
            block.get("text", "")
            for block in self.response.get("content", [])
            if block.get("type") == "text"
        )


class LLMClient:
    def __init__(
        self,
        *,
        guard: BudgetGuard,
        cache: OutputCache,
        estimator: Estimator,
        api_key: str | None,
        offline: bool = False,
        device: str = "unknown",
        sdk_factory: SdkFactory = default_sdk_factory,
    ) -> None:
        self.guard = guard
        self.cache = cache
        self.estimator = estimator
        self._api_key = api_key
        self.offline = offline
        self.device = device
        self._sdk_factory = sdk_factory
        self._sdk: Any = None

    def _client(self) -> Any:
        if self._sdk is None:
            if not self._api_key:
                raise MissingApiKey(
                    "AIPAYBACK_API_KEY is not set in .env. (ANTHROPIC_API_KEY is never used.)"
                )
            self._sdk = self._sdk_factory(self._api_key)
        return self._sdk

    def create(
        self,
        *,
        run: Run,
        stage: str,
        prompt_version: str,
        params: dict,
        shard: str = "misc",
    ) -> LLMResult:
        key = CacheKey(input_hash(params), prompt_version, params["model"])
        hit = self.cache.get(stage, key)
        if hit is not None:
            return LLMResult(
                response=hit["response"], cached=True, call_id=hit["call_id"], cost_usd=Decimal(0)
            )
        if self.offline:
            raise OfflineCacheMiss(
                f"Offline mode: no cached output for stage={stage} key={key.id}. "
                "Nothing was sent to the API."
            )

        self.guard.check_prompt_size(self.estimator.input_tokens(params))
        run.authorize_call(self.estimator.worst_case_cost(self.guard.pricing, params, batch=False))

        client = self._client()
        call_id = uuid.uuid4().hex
        started = time.perf_counter()
        try:
            message = client.messages.create(**params)
        except Exception:
            self._record(
                call_id, run, stage, prompt_version, key, TokenUsage(), 0, None, Decimal(0), "error"
            )
            raise
        latency_ms = int((time.perf_counter() - started) * 1000)

        usage, thinking = usage_from_sdk(message.usage)
        cost = self.guard.pricing.cost(params["model"], usage, batch=False)
        status = "refusal" if getattr(message, "stop_reason", None) == "refusal" else "ok"
        self._record(
            call_id, run, stage, prompt_version, key, usage, thinking, latency_ms, cost, status
        )
        run.record_spend(cost)

        response = message.model_dump(mode="json")
        if status == "ok":
            self.cache.put(stage, shard, key, response, call_id)
        return LLMResult(response=response, cached=False, call_id=call_id, cost_usd=cost)

    def _record(
        self,
        call_id: str,
        run: Run,
        stage: str,
        prompt_version: str,
        key: CacheKey,
        usage: TokenUsage,
        thinking: int,
        latency_ms: int | None,
        cost: Decimal,
        status: str,
    ) -> None:
        self.guard.ledger.append_call(
            CallRecord(
                call_id=call_id,
                ts=utc_now(),
                run_id=run.run_id,
                stage=stage,
                model=key.model,
                prompt_version=prompt_version,
                input_hash=key.input_hash,
                is_batch=False,
                batch_id=None,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_tokens=usage.cache_read_tokens,
                cache_write_5m_tokens=usage.cache_write_5m_tokens,
                cache_write_1h_tokens=usage.cache_write_1h_tokens,
                thinking_tokens=thinking,
                latency_ms=latency_ms,
                cost_usd=cost,
                status=status,
                device=self.device,
            )
        )
