"""Append-only spend ledger, committed to git so every device and the cron job share it.

Two JSONL files in data/ledger/ (both use `merge=union` in .gitattributes):
- llm_calls.jsonl: one line per billed API call (the source of truth for spend)
- runs.jsonl: run start/finish events; an unfinished run holds a reservation

Lines are always written with LF endings and sorted keys, so git merges stay clean.
Reads dedupe by id (union merges can duplicate lines) and fail closed on corrupt lines.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path


class LedgerCorrupt(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True)
class CallRecord:
    call_id: str
    ts: str
    run_id: str
    stage: str
    model: str
    prompt_version: str
    input_hash: str
    is_batch: bool
    batch_id: str | None
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_5m_tokens: int
    cache_write_1h_tokens: int
    thinking_tokens: int
    latency_ms: int | None
    cost_usd: Decimal
    status: str  # ok | refusal | error
    device: str

    def to_json(self) -> str:
        data = asdict(self)
        data["cost_usd"] = str(self.cost_usd)
        return json.dumps(data, sort_keys=True, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict) -> CallRecord:
        data = dict(data)
        data["cost_usd"] = Decimal(data["cost_usd"])
        return cls(**data)


@dataclass(frozen=True)
class RunEvent:
    event: str  # start | finish
    run_id: str
    ts: str
    command: str = ""
    stage: str = ""
    estimate_usd: Decimal = Decimal("0")
    reserved_usd: Decimal = Decimal("0")
    git_sha: str = ""
    device: str = ""
    status: str = ""  # finish only: ok | error | released

    def to_json(self) -> str:
        data = asdict(self)
        data["estimate_usd"] = str(self.estimate_usd)
        data["reserved_usd"] = str(self.reserved_usd)
        return json.dumps(data, sort_keys=True, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict) -> RunEvent:
        data = dict(data)
        data["estimate_usd"] = Decimal(data.get("estimate_usd", "0"))
        data["reserved_usd"] = Decimal(data.get("reserved_usd", "0"))
        return cls(**data)


@dataclass
class RunState:
    run_id: str
    start: RunEvent
    finish: RunEvent | None = None
    spent_usd: Decimal = Decimal("0")
    calls: int = 0

    @property
    def is_open(self) -> bool:
        return self.finish is None

    @property
    def outstanding_reservation(self) -> Decimal:
        """Reserved money not yet turned into recorded spend (zero once the run finishes)."""
        if not self.is_open:
            return Decimal("0")
        return max(self.start.reserved_usd - self.spent_usd, Decimal("0"))


@dataclass
class Ledger:
    directory: Path
    _calls_cache: list[CallRecord] | None = field(default=None, repr=False)

    @property
    def calls_path(self) -> Path:
        return self.directory / "llm_calls.jsonl"

    @property
    def runs_path(self) -> Path:
        return self.directory / "runs.jsonl"

    # writing -----------------------------------------------------------------

    def _append(self, path: Path, line: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def append_call(self, record: CallRecord) -> None:
        self._append(self.calls_path, record.to_json())
        self._calls_cache = None

    def append_run_event(self, event: RunEvent) -> None:
        self._append(self.runs_path, event.to_json())

    # reading -----------------------------------------------------------------

    @staticmethod
    def _read_jsonl(path: Path) -> Iterator[dict]:
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                text = line.strip()
                if not text:
                    continue
                try:
                    yield json.loads(text)
                except json.JSONDecodeError as exc:
                    raise LedgerCorrupt(
                        f"{path.name} line {lineno} is not valid JSON (merge conflict?). "
                        "Fix it before spending anything."
                    ) from exc

    def calls(self) -> list[CallRecord]:
        if self._calls_cache is None:
            seen: dict[str, CallRecord] = {}
            for data in self._read_jsonl(self.calls_path):
                rec = CallRecord.from_dict(data)
                seen.setdefault(rec.call_id, rec)
            self._calls_cache = list(seen.values())
        return list(self._calls_cache)

    def runs(self) -> dict[str, RunState]:
        states: dict[str, RunState] = {}
        for data in self._read_jsonl(self.runs_path):
            ev = RunEvent.from_dict(data)
            if ev.event == "start":
                states.setdefault(ev.run_id, RunState(run_id=ev.run_id, start=ev))
            elif ev.event == "finish":
                state = states.get(ev.run_id)
                if state is None:
                    raise LedgerCorrupt(f"runs.jsonl: finish for unknown run {ev.run_id}")
                state.finish = state.finish or ev
            else:
                raise LedgerCorrupt(f"runs.jsonl: unknown event {ev.event!r}")
        for rec in self.calls():
            state = states.get(rec.run_id)
            if state is not None:
                state.spent_usd += rec.cost_usd
                state.calls += 1
        return states

    def total_spent(self) -> Decimal:
        return sum((c.cost_usd for c in self.calls()), Decimal("0"))

    def outstanding_reservations(self) -> Decimal:
        return sum((r.outstanding_reservation for r in self.runs().values()), Decimal("0"))
