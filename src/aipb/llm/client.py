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
from pathlib import Path
from typing import Any

from aipb import jsonl
from aipb.budget.estimator import Estimator
from aipb.budget.guard import BudgetGuard, Run
from aipb.budget.ledger import CallRecord, utc_now
from aipb.budget.pricing import TokenUsage
from aipb.llm.cache import CacheKey, OutputCache, input_hash


class OfflineCacheMiss(RuntimeError):
    pass


@dataclass(frozen=True)
class Request:
    """One request in a stage run. `key` is the caller's id (e.g. a passage id)."""

    key: str
    params: dict
    shard: str = "misc"


@dataclass(frozen=True)
class Plan:
    total: int
    cached: int
    to_send: int
    worst_case_usd: Decimal


def custom_id(stage: str, input_hash_hex: str) -> str:
    """Batch custom_id: [a-zA-Z0-9_-], at most 64 characters, unique per request body."""
    prefix = "".join(c for c in stage if c.isalnum() or c in "_-")[:12]
    return f"{prefix}-{input_hash_hex[:48]}"


class BatchLog:
    """Committed log of submitted batches (data/ledger/batches.jsonl, union merge).

    A submitted batch is billed whether or not this process stays alive to read it, so
    its id and request map are written down before waiting.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def _events(self) -> list[dict]:
        return list(jsonl.read(self.path))

    def submitted(
        self, batch_id: str, run_id: str, stage: str, prompt_version: str, requests: dict
    ) -> None:
        event = {
            "event": "submit",
            "batch_id": batch_id,
            "run_id": run_id,
            "stage": stage,
            "prompt_version": prompt_version,
            "ts": utc_now(),
            "requests": requests,
        }
        jsonl.append(self.path, [event])

    def collected(self, batch_id: str) -> None:
        jsonl.append(self.path, [{"event": "collected", "batch_id": batch_id, "ts": utc_now()}])

    def submission(self, batch_id: str) -> dict | None:
        for e in self._events():
            if e["event"] == "submit" and e["batch_id"] == batch_id:
                return e
        return None

    def is_collected(self, batch_id: str) -> bool:
        return any(e["event"] == "collected" and e["batch_id"] == batch_id for e in self._events())

    def uncollected(self) -> list[dict]:
        events = self._events()
        done = {e["batch_id"] for e in events if e["event"] == "collected"}
        out, seen = [], set()
        for e in events:
            if e["event"] == "submit" and e["batch_id"] not in done | seen:
                seen.add(e["batch_id"])
                out.append(e)
        return out


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
    status: str = "ok"  # ok | refusal | errored | expired | canceled

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
        batch_log: BatchLog | None = None,
    ) -> None:
        self.batch_log = batch_log or BatchLog(guard.ledger.calls_path.parent / "batches.jsonl")
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
        return LLMResult(
            response=response, cached=False, call_id=call_id, cost_usd=cost, status=status
        )

    # ------------------------------------------------------------------ many requests

    def plan(self, stage: str, prompt_version: str, items: list[Request], *, batch: bool) -> Plan:
        """What a run would cost before anything is sent: cache hits are free."""
        misses: dict[str, Request] = {}
        hits = 0
        for item in items:
            key = CacheKey(input_hash(item.params), prompt_version, item.params["model"])
            if self.cache.get(stage, key) is not None:
                hits += 1
            else:
                misses.setdefault(key.id, item)
        worst = Decimal(0)
        for r in misses.values():
            worst += self.estimator.worst_case_cost(self.guard.pricing, r.params, batch=batch)
        return Plan(total=len(items), cached=hits, to_send=len(misses), worst_case_usd=worst)

    def run_many(
        self,
        *,
        run: Run | None,
        stage: str,
        prompt_version: str,
        items: list[Request],
        batch: bool,
        poll_seconds: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
        log: Callable[[str], None] = lambda _m: None,
    ) -> dict[str, LLMResult]:
        """Results for every item, keyed by item.key. Cache hits never reach the API.

        batch=True sends all misses as one Message Batch (50% off). The batch id is
        written to the committed batch log before waiting, so an interrupted run can be
        collected later with `aipb batch-collect` instead of paying again.
        """
        results: dict[str, LLMResult] = {}
        pending: dict[str, list[Request]] = {}
        for item in items:
            key = CacheKey(input_hash(item.params), prompt_version, item.params["model"])
            hit = self.cache.get(stage, key)
            if hit is not None:
                results[item.key] = LLMResult(
                    response=hit["response"],
                    cached=True,
                    call_id=hit["call_id"],
                    cost_usd=Decimal(0),
                )
            else:
                pending.setdefault(key.input_hash, []).append(item)
        if not pending:
            return results
        if self.offline:
            raise OfflineCacheMiss(
                f"Offline mode: {len(pending)} request(s) for stage={stage} are not cached. "
                "Nothing was sent to the API."
            )
        if run is None:
            raise RuntimeError("A budget run is required for requests that are not cached.")
        if not batch:
            for group in pending.values():
                res = self.create(
                    run=run,
                    stage=stage,
                    prompt_version=prompt_version,
                    params=group[0].params,
                    shard=group[0].shard,
                )
                for item in group:
                    results[item.key] = res
            return results

        worst = Decimal(0)
        meta: dict[str, dict] = {}
        requests = []
        for h, group in pending.items():
            first = group[0]
            self.guard.check_prompt_size(self.estimator.input_tokens(first.params))
            worst += self.estimator.worst_case_cost(self.guard.pricing, first.params, batch=True)
            cid = custom_id(stage, h)
            meta[cid] = {"input_hash": h, "model": first.params["model"], "shard": first.shard}
            requests.append({"custom_id": cid, "params": first.params})
        run.authorize_call(worst)
        client = self._client()
        created = client.messages.batches.create(requests=requests)
        batch_id = created.id
        self.batch_log.submitted(batch_id, run.run_id, stage, prompt_version, meta)
        log(f"Submitted batch {batch_id} with {len(requests)} requests; waiting for results.")
        try:
            while client.messages.batches.retrieve(batch_id).processing_status != "ended":
                sleep(poll_seconds)
            by_cid = self.collect(batch_id, run=run)
        except BaseException:
            run.hold()  # billed even if we stop waiting: keep the reservation (fail closed)
            raise
        for h, group in pending.items():
            res = by_cid.get(custom_id(stage, h)) or LLMResult(
                {}, False, None, Decimal(0), status="errored"
            )
            for item in group:
                results[item.key] = res
        return results

    def collect(self, batch_id: str, *, run: Run | None = None) -> dict[str, LLMResult]:
        """Settle an ended batch: one ledger line per request, successes cached."""
        sub = self.batch_log.submission(batch_id)
        if sub is None:
            raise RuntimeError(f"Batch {batch_id} is not in the batch log.")
        if self.batch_log.is_collected(batch_id):
            raise RuntimeError(f"Batch {batch_id} was already collected; its outputs are cached.")
        stage, prompt_version, meta = sub["stage"], sub["prompt_version"], sub["requests"]
        client = self._client()
        out: dict[str, LLMResult] = {}
        spent = Decimal(0)
        for entry in client.messages.batches.results(batch_id):
            info = meta.get(entry.custom_id)
            if info is None:
                continue
            key = CacheKey(info["input_hash"], prompt_version, info["model"])
            call_id = uuid.uuid4().hex
            rtype = entry.result.type
            if rtype != "succeeded":
                self._record_raw(
                    call_id, sub["run_id"], stage, prompt_version, key, TokenUsage(), 0, None,
                    Decimal(0), rtype, batch_id,
                )  # fmt: skip
                out[entry.custom_id] = LLMResult({}, False, call_id, Decimal(0), status=rtype)
                continue
            message = entry.result.message
            usage, thinking = usage_from_sdk(message.usage)
            cost = self.guard.pricing.cost(info["model"], usage, batch=True)
            status = "refusal" if getattr(message, "stop_reason", None) == "refusal" else "ok"
            self._record_raw(
                call_id, sub["run_id"], stage, prompt_version, key, usage, thinking, None, cost,
                status, batch_id,
            )  # fmt: skip
            spent += cost
            response = message.model_dump(mode="json")
            if status == "ok":
                self.cache.put(stage, info["shard"], key, response, call_id)
            out[entry.custom_id] = LLMResult(response, False, call_id, cost, status=status)
        if run is not None:
            run.record_spend(spent)
        self.batch_log.collected(batch_id)
        state = self.guard.ledger.runs().get(sub["run_id"])
        if run is None and state is not None and state.is_open:
            self.guard.finish_run(sub["run_id"], "collected")  # release the held reservation
        return out

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
        self._record_raw(
            call_id, run.run_id, stage, prompt_version, key, usage, thinking, latency_ms, cost,
            status, None,
        )  # fmt: skip

    def _record_raw(
        self,
        call_id: str,
        run_id: str,
        stage: str,
        prompt_version: str,
        key: CacheKey,
        usage: TokenUsage,
        thinking: int,
        latency_ms: int | None,
        cost: Decimal,
        status: str,
        batch_id: str | None,
    ) -> None:
        self.guard.ledger.append_call(
            CallRecord(
                call_id=call_id,
                ts=utc_now(),
                run_id=run_id,
                stage=stage,
                model=key.model,
                prompt_version=prompt_version,
                input_hash=key.input_hash,
                is_batch=batch_id is not None,
                batch_id=batch_id,
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
