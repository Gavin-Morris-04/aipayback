"""Corrections to the gold labels from Nick's reviews (evals/gold/corrections.yaml).

His returned workbooks stay exactly as he saved them; `aipb eval` applies these on top, and
each entry records which review row it came from and why. Every corrected or added quote
must appear verbatim in the passage, so a correction can't bring in words the filing
doesn't have.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import yaml

FILE = "corrections.yaml"
CLASSES = ("promise", "hype", "none")


class CorrectionError(ValueError):
    pass


def load(gold_dir: Path) -> list[dict]:
    path = gold_dir / FILE
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(data.get("corrections") or [])


def _check_quote(text: str, quote: str, where: str) -> None:
    if not quote or quote not in text:
        raise CorrectionError(f"{where}: quote not verbatim in the passage: {quote[:80]!r}")


def apply(gold: list, corrections: list[dict]) -> list:
    """Gold passages with corrections applied. Entries for passages outside `gold` (other
    companies or splits) are skipped; an entry that doesn't fit its passage is an error."""
    by_id = {g.passage_id: g for g in gold}
    excluded: set[str] = set()
    for c in corrections:
        pid = c.get("passage_id", "")
        where = f"{FILE} {pid} ({c.get('source', 'no source')})"
        if not c.get("source") or not c.get("reason"):
            raise CorrectionError(f"{where}: every correction needs a source and a reason")
        g = by_id.get(pid)
        if g is None:
            continue
        if c.get("exclude"):
            excluded.add(pid)
            continue
        label = c.get("set_label") or g.label
        if label not in CLASSES:
            raise CorrectionError(f"{where}: set_label must be one of {', '.join(CLASSES)}")
        promises = [dict(p) for p in g.promises]
        for fix in c.get("fix_quotes") or []:
            hits = [p for p in promises if p.get("quote") == fix.get("from")]
            if not hits:
                raise CorrectionError(f"{where}: no gold quote {fix.get('from', '')[:60]!r}")
            _check_quote(g.text, fix.get("to", ""), where)
            for p in hits:
                p["quote"] = fix["to"]
        for add in c.get("add_promises") or []:
            _check_quote(g.text, add.get("quote", ""), where)
            promises.append(
                {
                    "row_id": f"correction:{pid}",
                    "passage_id": pid,
                    "ticker": g.ticker,
                    "promise_n": str(len(promises) + 1),
                    "quote": add["quote"],
                    "claim_type": add.get("claim_type", ""),
                    "metric": add.get("metric", ""),
                    "target": add.get("target", ""),
                    "deadline": add.get("deadline", ""),
                }
            )
        by_id[pid] = replace(g, label=label, promises=promises)
    return [by_id[g.passage_id] for g in gold if g.passage_id not in excluded]
