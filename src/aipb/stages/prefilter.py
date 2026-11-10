"""Stage 3a: keyword + forward-cue prefilter and boilerplate dedup. Plain code, $0.

Dedup is deliberately conservative. Two passages count as duplicates only when they are
near-identical (word 5-gram Jaccard >= 0.9) AND contain exactly the same numbers. A
restated promise with a changed target ("$3.5 billion" -> "$4.5 billion") or a changed
date is never hidden as boilerplate: those edits are exactly what verification looks for.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from aipb.parse.passages import normalize_for_match

JACCARD_THRESHOLD = 0.9
SHINGLE = 5
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _combine(patterns: list[str], flags: int) -> re.Pattern | None:
    if not patterns:
        return None
    for p in patterns:  # fail early, naming the bad pattern
        re.compile(p, flags)
    return re.compile("|".join(f"(?:{p})" for p in patterns), flags)


@dataclass
class Lexicon:
    version: str
    ai: list[re.Pattern]
    fwd: list[re.Pattern]

    @classmethod
    def load(cls, path: Path) -> Lexicon:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        # One alternation per list is ~10x faster than one regex per term. Whether a
        # passage has any hit is unchanged; overlapping terms ("Gen AI" vs "AI") may be
        # reported once instead of twice.
        ai = [
            _combine(cfg.get("ai_terms", []), re.IGNORECASE),
            _combine(cfg.get("ai_terms_case_sensitive", []), 0),
        ]
        fwd = [_combine(cfg.get("forward_cues", []), re.IGNORECASE)]
        return cls(str(cfg.get("version", "kw?")), [p for p in ai if p], [p for p in fwd if p])

    @staticmethod
    def _hits(patterns: list[re.Pattern], text: str) -> list[str]:
        found: dict[str, None] = {}
        for pat in patterns:
            for m in pat.finditer(text):
                found.setdefault(m.group(0).lower(), None)
        return sorted(found)

    def scan(self, text: str) -> tuple[list[str], list[str]]:
        norm = normalize_for_match(text)
        return self._hits(self.ai, norm), self._hits(self.fwd, norm)


def numbers_in(text: str) -> tuple[str, ...]:
    return tuple(sorted(n.replace(",", "") for n in _NUMBER.findall(text)))


def shingles(text: str, k: int = SHINGLE) -> frozenset[str]:
    words = re.findall(r"[a-z0-9]+", normalize_for_match(text).lower())
    if len(words) < k:
        return frozenset([" ".join(words)])
    return frozenset(" ".join(words[i : i + k]) for i in range(len(words) - k + 1))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


@dataclass
class _Canon:
    passage_id: str
    shingles: frozenset[str]
    numbers: tuple[str, ...]


@dataclass
class Deduper:
    """Feed passages in filing order; the first of each near-duplicate group is canonical."""

    threshold: float = JACCARD_THRESHOLD
    _exact: dict[str, str] = field(default_factory=dict)
    _canon: list[_Canon] = field(default_factory=list)

    def check(self, passage_id: str, text: str) -> str | None:
        """Return the passage_id this one duplicates, or None if it is new."""
        norm = normalize_for_match(text).lower()
        if norm in self._exact:
            return self._exact[norm]
        if self.threshold > 1.0:  # exact-only mode
            self._exact[norm] = passage_id
            return None
        sh = shingles(text)
        nums = numbers_in(norm)
        for c in self._canon:
            if c.numbers == nums and jaccard(sh, c.shingles) >= self.threshold:
                self._exact[norm] = c.passage_id
                return c.passage_id
        self._exact[norm] = passage_id
        self._canon.append(_Canon(passage_id, sh, nums))
        return None
