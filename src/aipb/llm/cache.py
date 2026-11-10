"""Never pay twice: every LLM output is stored, keyed by (input hash, prompt version, model).

Outputs live in data/outputs/<stage>/<shard>.jsonl and are committed to git, so any
device (or CI, in offline mode) can replay them with zero API calls.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aipb.budget.ledger import LedgerCorrupt, utc_now


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def input_hash(params: dict) -> str:
    return hashlib.sha256(canonical_json(params).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CacheKey:
    input_hash: str
    prompt_version: str
    model: str

    @property
    def id(self) -> str:
        return f"{self.model}|{self.prompt_version}|{self.input_hash}"


@dataclass
class OutputCache:
    directory: Path
    _index: dict[str, dict[str, dict]] = field(default_factory=dict, repr=False)

    def _stage_dir(self, stage: str) -> Path:
        return self.directory / stage

    def _load(self, stage: str) -> dict[str, dict]:
        if stage in self._index:
            return self._index[stage]
        index: dict[str, dict] = {}
        stage_dir = self._stage_dir(stage)
        if stage_dir.is_dir():
            for path in sorted(stage_dir.glob("*.jsonl")):
                with path.open("r", encoding="utf-8") as fh:
                    for lineno, line in enumerate(fh, start=1):
                        text = line.strip()
                        if not text:
                            continue
                        try:
                            rec = json.loads(text)
                        except json.JSONDecodeError as exc:
                            raise LedgerCorrupt(
                                f"{path} line {lineno} is not valid JSON (merge conflict?)"
                            ) from exc
                        index.setdefault(rec["key"], rec)
        self._index[stage] = index
        return index

    def get(self, stage: str, key: CacheKey) -> dict | None:
        return self._load(stage).get(key.id)

    def put(self, stage: str, shard: str, key: CacheKey, response: dict, call_id: str) -> None:
        record = {
            "key": key.id,
            "input_hash": key.input_hash,
            "prompt_version": key.prompt_version,
            "model": key.model,
            "stage": stage,
            "call_id": call_id,
            "created": utc_now(),
            "response": response,
        }
        path = self._stage_dir(stage) / f"{shard}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
        self._load(stage)[key.id] = record

    def count(self, stage: str) -> int:
        return len(self._load(stage))
