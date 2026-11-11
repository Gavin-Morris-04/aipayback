"""Matching and metrics. Small samples, so every headline number carries a 95% interval."""

from __future__ import annotations

import math
import random
import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from aipb.parse.passages import normalize_for_match

IOU_THRESHOLD = 0.5


def span_in(text_norm: str, quote: str) -> tuple[int, int] | None:
    """Span of a quote inside normalized passage text (exact, then case-insensitive)."""
    q = normalize_for_match(quote)
    if not q:
        return None
    i = text_norm.find(q)
    if i < 0:
        i = text_norm.lower().find(q.lower())
    return (i, i + len(q)) if i >= 0 else None


def iou(a: tuple[int, int], b: tuple[int, int]) -> float:
    inter = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return inter / union if union else 0.0


@dataclass
class Match:
    gold: dict
    pred: dict
    iou: float


def match_passage(
    text: str, gold: list[dict], pred: list[dict]
) -> tuple[list[Match], list[dict], list[dict]]:
    """Greedy best-IoU matching within one passage. Returns matches, missed gold, extra pred."""
    norm = normalize_for_match(text)
    g_spans = [(g, span_in(norm, g["quote"])) for g in gold]
    p_spans = [(p, span_in(norm, p["quote"])) for p in pred]
    pairs = []
    for gi, (_, gs) in enumerate(g_spans):
        for pi, (_, ps) in enumerate(p_spans):
            if gs and ps:
                score = iou(gs, ps)
                if score >= IOU_THRESHOLD:
                    pairs.append((score, gi, pi))
    pairs.sort(reverse=True)
    used_g, used_p, matches = set(), set(), []
    for score, gi, pi in pairs:
        if gi in used_g or pi in used_p:
            continue
        used_g.add(gi)
        used_p.add(pi)
        matches.append(Match(g_spans[gi][0], p_spans[pi][0], score))
    missed = [g for i, (g, _) in enumerate(g_spans) if i not in used_g]
    extra = [p for i, (p, _) in enumerate(p_spans) if i not in used_p]
    return matches, missed, extra


def prf(tp: int, fp: int, fn: int) -> dict[str, float | None]:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f = 2 * p * r / (p + r) if p and r else (0.0 if p is not None and r is not None else None)
    return {"precision": p, "recall": r, "f1": f}


def bootstrap(
    units: list, stat: Callable[[list], float | None], *, n: int = 1000, seed: int = 7
) -> tuple[float, float] | None:
    """95% percentile interval of stat() over resamples of units (e.g. passages)."""
    if not units:
        return None
    rng = random.Random(seed)
    values = []
    for _ in range(n):
        sample = [units[rng.randrange(len(units))] for _ in units]
        v = stat(sample)
        if v is not None:
            values.append(v)
    if not values:
        return None
    values.sort()
    return values[int(0.025 * (len(values) - 1))], values[int(0.975 * (len(values) - 1))]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n == 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    lo = 0.0 if k == 0 else max(0.0, centre - half)
    hi = 1.0 if k == n else min(1.0, centre + half)
    return lo, hi


_SCALE = {"thousand": 1e3, "million": 1e6, "billion": 1e9, "trillion": 1e12}


def number_of(text: str | None) -> float | None:
    """First number in a target like "$150 million" -> 150000000.0; "10 percent" -> 10."""
    if not text:
        return None
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*(thousand|million|billion|trillion)?", text.lower())
    if not m:
        return None
    value = float(m.group(1).replace(",", ""))
    return value * _SCALE.get(m.group(2) or "", 1.0)


def year_of(text: str | None) -> int | None:
    m = re.search(r"\b(20\d\d)\b", text or "")
    return int(m.group(1)) if m else None


def field_agreement(matches: list[Match]) -> dict[str, dict]:
    """Accuracy of claim type, target number and deadline year on matched promises."""
    out: dict[str, dict] = {}

    def pred_number(p: dict) -> float | None:
        return p.get("target_value") or number_of(p.get("target_text"))

    def pred_year(p: dict) -> int | None:
        return p.get("deadline_year") or year_of(p.get("deadline_text"))

    checks = {
        "claim_type": lambda g, p: g["claim_type"] == p["claim_type"],
        "target": lambda g, p: _same_number(number_of(g.get("target")), pred_number(p)),
        "deadline_year": lambda g, p: year_of(g.get("deadline")) == pred_year(p),
    }
    for name, ok in checks.items():
        relevant = [m for m in matches if name == "claim_type" or _gold_has(m.gold, name)]
        hits = sum(1 for m in relevant if ok(m.gold, m.pred))
        out[name] = {"n": len(relevant), "correct": hits,
                     "accuracy": hits / len(relevant) if relevant else None}  # fmt: skip
    return out


def _gold_has(g: dict, name: str) -> bool:
    if name == "target":
        return number_of(g.get("target")) is not None
    return year_of(g.get("deadline")) is not None


def _same_number(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= 0.01 * max(abs(a), abs(b), 1e-9)


@dataclass
class Confusion:
    labels: tuple[str, ...]
    counts: dict[tuple[str, str], int] = field(default_factory=lambda: defaultdict(int))

    def add(self, gold: str, pred: str) -> None:
        self.counts[(gold, pred)] += 1

    def table(self) -> dict[str, dict[str, int]]:
        preds = sorted({p for _, p in self.counts} | set(self.labels))
        return {g: {p: self.counts.get((g, p), 0) for p in preds} for g in self.labels}

    def accuracy(self) -> float | None:
        total = sum(self.counts.values())
        right = sum(v for (g, p), v in self.counts.items() if g == p)
        return right / total if total else None

    def recall(self, label: str) -> float | None:
        row = {p: v for (g, p), v in self.counts.items() if g == label}
        n = sum(row.values())
        return row.get(label, 0) / n if n else None
