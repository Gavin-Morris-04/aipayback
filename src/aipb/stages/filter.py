"""Stage 3b: Haiku classifies keyword passages as promise / hype / none (batched, cached).

Only canonical (deduplicated) keyword passages from promise-window filings are sent.
Passages are packed up to `group_size` per request, always from the SAME filing and in a
fixed order, so adding new filings later never changes (and never re-pays for) the
requests made for old ones.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field

from aipb.labeling.schema import PROMISE_WINDOW, section_name
from aipb.llm.client import LLMResult, Request
from aipb.llm.params import OutputError, Prompt, build_params, obj, parse_json

STAGE = "filter"
LABELS = ("promise", "hype", "none")

SCHEMA = obj(
    {
        "items": {
            "type": "array",
            "items": obj(
                {
                    "id": {"type": "string"},
                    "label": {"type": "string", "enum": list(LABELS)},
                    "confidence": {"type": "string", "enum": ["high", "low"]},
                }
            ),
        }
    }
)


@dataclass
class Group:
    key: str
    cik: int
    passage_ids: list[str]


@dataclass
class FilterStats:
    passages: int = 0
    requests: int = 0
    by_label: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    errors: list[str] = field(default_factory=list)


def candidates(
    conn: sqlite3.Connection, ciks: list[int], passage_ids: set[str] | None = None
) -> list[sqlite3.Row]:
    marks = ",".join("?" * len(ciks))
    rows = conn.execute(
        f"""
        SELECT p.passage_id, p.cik, p.accession, p.form, p.filing_date, p.section, p.text,
               c.ticker, c.name
        FROM passages p JOIN companies c ON c.cik = p.cik
        WHERE p.cik IN ({marks}) AND p.dup_of IS NULL AND p.kw_hits IS NOT NULL
          AND p.kw_hits != '[]' AND p.filing_date BETWEEN ? AND ?
        ORDER BY p.cik, p.filing_date, p.accession, p.char_start
        """,
        (*ciks, *PROMISE_WINDOW),
    ).fetchall()
    if passage_ids is not None:
        rows = [r for r in rows if r["passage_id"] in passage_ids]
    return rows


def _passage_block(local_id: str, r: sqlite3.Row) -> str:
    return (
        f'<passage id="{local_id}" company="{r["name"]} ({r["ticker"]})" form="{r["form"]}" '
        f'filed="{r["filing_date"]}" section="{section_name(r["section"])}">\n'
        f"{r['text']}\n</passage>"
    )


def build_requests(
    rows: list[sqlite3.Row], cfg: dict, prompt: Prompt
) -> tuple[list[Request], dict[str, Group]]:
    by_filing: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for r in rows:
        by_filing[r["accession"]].append(r)
    size = int(cfg.get("group_size", 10))
    requests: list[Request] = []
    groups: dict[str, Group] = {}
    for accession, items in by_filing.items():
        for start in range(0, len(items), size):
            chunk = items[start : start + size]
            key = f"{accession}#{start // size:03d}"
            blocks = [_passage_block(f"P{i}", r) for i, r in enumerate(chunk, start=1)]
            content = f"Classify each of these {len(chunk)} passages.\n\n" + "\n\n".join(blocks)
            params = build_params(cfg, prompt, content, SCHEMA)
            requests.append(Request(key=key, params=params, shard=str(chunk[0]["cik"])))
            groups[key] = Group(key, chunk[0]["cik"], [r["passage_id"] for r in chunk])
    return requests, groups


def store_results(
    conn: sqlite3.Connection,
    groups: dict[str, Group],
    results: dict[str, LLMResult],
    *,
    variant: str,
    prompt_id: str,
    model: str,
) -> FilterStats:
    stats = FilterStats(requests=len(groups))
    rows = []
    for key, group in groups.items():
        labels: dict[str, tuple[str, str]] = {}
        try:
            data = parse_json(results[key])
            for item in data.get("items", []):
                if item.get("label") in LABELS:
                    labels[str(item.get("id"))] = (item["label"], item.get("confidence", "low"))
        except (OutputError, KeyError) as exc:
            stats.errors.append(f"{key}: {exc}")
        for i, pid in enumerate(group.passage_ids, start=1):
            label, conf = labels.get(f"P{i}", ("error", None))
            stats.passages += 1
            stats.by_label[label] += 1
            rows.append((pid, variant, label, conf, prompt_id, model))
    with conn:
        conn.executemany(
            "INSERT INTO classifications VALUES (?,?,?,?,?,?) ON CONFLICT(passage_id, variant) "
            "DO UPDATE SET label=excluded.label, confidence=excluded.confidence, "
            "prompt_version=excluded.prompt_version, model=excluded.model",
            rows,
        )
    return stats


def routed_to_extraction(cfg: dict, label: str, confidence: str | None) -> bool:
    """Recall first: promises, unsure answers and failed classifications all go on."""
    if label == "error":
        return True
    if label in cfg.get("extract_labels", ["promise"]):
        return True
    return bool(cfg.get("extract_low_confidence", True)) and confidence == "low"
