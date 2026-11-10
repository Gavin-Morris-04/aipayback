"""JSONL helpers for committed files: UTF-8, LF line endings, one JSON object per line."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path


def dumps(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def append(path: Path, records: Iterable[dict]) -> int:
    lines = [dumps(r) + "\n" for r in records]
    if not lines:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.writelines(lines)
    return len(lines)


def write(path: Path, records: Iterable[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for r in records:
            fh.write(dumps(r) + "\n")
            n += 1
    return n


def read(path: Path) -> Iterator[dict]:
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
                raise ValueError(
                    f"{path} line {lineno} is not valid JSON (merge conflict?)"
                ) from exc
