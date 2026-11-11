"""`aipb eval-status`: statuses vs Nick's gold labels, and precision vs coverage. $0.

Gold rows are matched to the pipeline's promise clusters by passage and quote overlap
(not by cluster id), so the eval survives re-extraction. Reported:
- verdict accuracy, per-class recall and confusion (the verdict the gate would use,
  ignoring the confidence threshold);
- published precision and coverage at the configured threshold: of the items that would
  be published, how many match gold, and what share gets published at all;
- the same pair at thresholds 0.50-0.95, which is how the threshold gets chosen.
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from aipb.evals import metrics as M
from aipb.labeling.status_packets import LABEL_TO_CODE
from aipb.verify import gate
from aipb.verify.tier1 import DISPLAY

CODES = ("delivered", "on_track", "no_evidence_yet", "walked_back", "walked_back_silent")


def _code(status: str, silent: bool) -> str:
    return "walked_back_silent" if status == "walked_back" and silent else status


def load_gold(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r["status"] in LABEL_TO_CODE]
    for r in rows:
        status, silent = LABEL_TO_CODE[r["status"]]
        r["code"] = _code(status, silent)
    return rows


def find_cluster(conn: sqlite3.Connection, g: dict, variant: str) -> str | None:
    text = conn.execute(
        "SELECT text FROM passages WHERE passage_id=?", (g["passage_id"],)
    ).fetchone()
    if text is None:
        return None
    best, best_iou = None, 0.0
    norm = M.normalize_for_match(text[0])
    gs = M.span_in(norm, g["quote"])
    for r in conn.execute(
        "SELECT quote, cluster_id FROM promises WHERE passage_id=? AND "
        "variant=? AND cluster_id IS NOT NULL",
        (g["passage_id"], variant),
    ):
        ps = M.span_in(norm, r["quote"])
        if gs and ps and (score := M.iou(gs, ps)) > best_iou:
            best, best_iou = r["cluster_id"], score
    return best if best_iou >= M.IOU_THRESHOLD else None


def evaluate(
    conn: sqlite3.Connection,
    gold: list[dict],
    *,
    variant: str,
    threshold: float,
    load_verdict,
    errors: set[str],
) -> dict:
    cm = M.Confusion(CODES)
    items = []
    unmatched = 0
    for g in gold:
        cid = find_cluster(conn, g, variant)
        if cid is None:
            unmatched += 1
            cm.add(g["code"], "not_extracted")
            continue
        t1 = load_verdict(conn, cid, variant, "1")
        t2 = load_verdict(conn, cid, variant, "2")
        from aipb.stages.verify_runner import load_explanation

        e = load_explanation(conn, cid, variant)
        exp_ok = bool(e and e["citations_valid"] and e["lint_ok"])
        best = max(
            (v for v in (t1, t2) if v is not None and v.valid),
            key=lambda v: v.confidence,
            default=None,
        )
        pred = _code(best.status, best.walked_back_kind == "silent") if best else "invalid"
        cm.add(g["code"], pred)
        items.append(
            {
                "gold": g["code"],
                "t1": t1,
                "t2": t2,
                "exp_ok": exp_ok,
                "cid": cid,
                "row_id": g["row_id"],
            }
        )

    def at(th: float) -> dict:
        published = correct = 0
        for it in items:
            d = gate.decide(
                it["t1"],
                it["t2"],
                explanation_ok=it["exp_ok"],
                open_error_report=it["cid"] in errors,
                threshold=th,
            )
            if d.publishable:
                published += 1
                correct += _code(d.status, d.silent) == it["gold"]
        n = len(gold)
        return {
            "threshold": th,
            "published": published,
            "correct": correct,
            "precision": correct / published if published else None,
            "precision_ci95": M.wilson(correct, published),
            "coverage": published / n if n else None,
        }

    return {
        "gold_items": len(gold),
        "matched_to_a_cluster": len(items),
        "not_extracted": unmatched,
        "verdict_accuracy": cm.accuracy(),
        "recall": {c: cm.recall(c) for c in CODES},
        "confusion": cm.table(),
        "at_threshold": at(threshold),
        "curve": [at(t / 100) for t in range(50, 100, 5)],
    }


def render(result: dict) -> str:
    a = result["at_threshold"]
    lines = [
        "# Status eval",
        "",
        f"Gold: {result['gold_items']} promises; matched to a pipeline promise: "
        f"{result['matched_to_a_cluster']}; not extracted: {result['not_extracted']}.",
        f"Verdict accuracy (before the gate): {_pct(result['verdict_accuracy'])}.",
        "",
        f"At threshold {a['threshold']}: published {a['published']} "
        f"(coverage {_pct(a['coverage'])}), precision {_pct(a['precision'])}.",
        "",
        "| Threshold | Published | Precision | Coverage |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {r['threshold']:.2f} | {r['published']} | {_pct(r['precision'])} | "
        f"{_pct(r['coverage'])} |"
        for r in result["curve"]
    ]
    lines += [
        "",
        "Per-class recall: "
        + ", ".join(f"{DISPLAY.get(k, k)}: {_pct(v)}" for k, v in result["recall"].items()),
    ]
    return "\n".join(lines) + "\n"


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"
