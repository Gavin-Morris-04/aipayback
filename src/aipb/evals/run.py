"""`aipb eval`: score the pipeline's outputs against Nick's gold labels. Costs $0.

Reads gold labels (evals/gold), the frozen split, and the stored predictions for one
variant. Writes evals/results/<timestamp>_<sha>.{json,md}, appends a row to the README's
eval history, and writes a disagreement workbook for review.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from aipb.budget.ledger import Ledger, utc_now
from aipb.evals import metrics as M
from aipb.labeling import schema as S

GOLD_TO_CLASS = {
    S.LABEL_PROMISE: "promise",
    S.LABEL_HYPE: "hype",
    S.LABEL_NONE: "none",
}
CLASSES = ("promise", "hype", "none")
README_START = "<!-- eval-history:start -->"
README_END = "<!-- eval-history:end -->"


class NoGold(RuntimeError):
    pass


@dataclass
class GoldPassage:
    passage_id: str
    ticker: str
    label: str  # promise | hype | none
    sampled_as: str
    text: str
    promises: list[dict]


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def load_gold(gold_dir: Path, tickers: set[str]) -> list[GoldPassage]:
    keys = {}
    for path in sorted((gold_dir / "packets" / S.PACKET_VERSION).glob("*_key.csv")):
        for row in _read_csv(path):
            keys[row["row_id"]] = row
    promises: dict[str, list[dict]] = defaultdict(list)
    for p in _read_csv(gold_dir / "promises.csv"):
        promises[p["row_id"]].append(p)
    out = []
    for row in _read_csv(gold_dir / "passages.csv"):
        label = GOLD_TO_CLASS.get(row["label"])
        if label is None or row["ticker"] not in tickers:
            continue  # Unsure rows and other companies are left out
        key = keys.get(row["row_id"])
        if key is None:
            continue
        out.append(
            GoldPassage(
                row["passage_id"],
                row["ticker"],
                label,
                row["sampled_as"],
                key["text"],
                promises.get(row["row_id"], []),
            )
        )
    return out


def _predictions(conn: sqlite3.Connection, variant: str, filter_variant: str, pids: list[str]):
    labels = {}
    for r in conn.execute(
        "SELECT passage_id, label, confidence FROM classifications WHERE variant=?",
        (filter_variant,),
    ):
        labels[r["passage_id"]] = (r["label"], r["confidence"])
    preds: dict[str, list[dict]] = defaultdict(list)
    for r in conn.execute("SELECT * FROM promises WHERE variant=?", (variant,)):
        preds[r["passage_id"]].append(dict(r))
    logs = {
        r["passage_id"]: dict(r)
        for r in conn.execute("SELECT * FROM extraction_log WHERE variant=?", (variant,))
    }
    return labels, preds, logs


def _passage_pred_class(preds: list[dict]) -> str:
    kinds = {p["kind"] for p in preds}
    return "promise" if "promise" in kinds else ("hype" if "hype" in kinds else "none")


def evaluate(
    conn: sqlite3.Connection,
    gold: list[GoldPassage],
    *,
    variant: str,
    filter_variant: str,
    route: callable,
    corpus_counts: dict[str, int],
) -> dict:
    pids = [g.passage_id for g in gold]
    labels, preds, logs = _predictions(conn, variant, filter_variant, pids)

    filter_cm = M.Confusion(CLASSES)
    e2e_cm = M.Confusion(CLASSES)
    per_passage = []  # (tp, fp, fn) for bootstrap
    all_matches: list[M.Match] = []
    disagreements = []
    routed_promise = 0
    gold_promise_passages = 0
    for g in gold:
        if g.sampled_as == "keyword":
            label, conf = labels.get(g.passage_id, ("not_classified", None))
            filter_cm.add(g.label, label)
            if g.label == "promise":
                gold_promise_passages += 1
                routed_promise += int(route(label, conf))
        pred_all = preds.get(g.passage_id, [])
        e2e_cm.add(g.label, _passage_pred_class(pred_all))
        pred_promises = [p for p in pred_all if p["kind"] == "promise"]
        gold_promises = g.promises if g.label == "promise" else []
        matches, missed, extra = M.match_passage(g.text, gold_promises, pred_promises)
        all_matches += matches
        per_passage.append((len(matches), len(extra), len(missed)))
        for m in missed:
            disagreements.append(_row(g, "missed promise", m.get("quote", ""), "", m))
        for p in extra:
            disagreements.append(_row(g, "extra promise", "", p["quote"], p))
        for m in matches:
            if m.gold["claim_type"] != m.pred["claim_type"]:
                disagreements.append(
                    _row(g, f"claim type: gold {m.gold['claim_type']}, model "
                            f"{m.pred['claim_type']}", m.gold["quote"], m.pred["quote"], m.pred)
                )  # fmt: skip

    tp, fp, fn = (sum(x[i] for x in per_passage) for i in range(3))
    scores = M.prf(tp, fp, fn)

    def stat(name):
        def f(sample):
            a, b, c = (sum(x[i] for x in sample) for i in range(3))
            return M.prf(a, b, c)[name]

        return f

    cis = {k: M.bootstrap(per_passage, stat(k)) for k in ("precision", "recall", "f1")}
    stored = sum(len(v) for v in preds.values())
    dropped = sum(int(v["n_dropped"]) for v in logs.values())

    # Prefilter recall from the random non-keyword rows.
    nonkw = [g for g in gold if g.sampled_as == "non_keyword"]
    kw = [g for g in gold if g.sampled_as == "keyword"]
    k_miss = sum(g.label == "promise" for g in nonkw)
    k_kw = sum(g.label == "promise" for g in kw)
    miss_rate = k_miss / len(nonkw) if nonkw else None
    est = None
    if nonkw and kw and corpus_counts.get("nonkw") and corpus_counts.get("kw"):
        missed_est = miss_rate * corpus_counts["nonkw"]
        found_est = k_kw / len(kw) * corpus_counts["kw"]
        est = found_est / (found_est + missed_est) if found_est + missed_est else None
    return {
        "gold": {
            "passages": len(gold),
            "keyword_passages": len(kw),
            "random_non_keyword_passages": len(nonkw),
            "promises": sum(len(g.promises) for g in gold if g.label == "promise"),
            "by_label": {c: sum(g.label == c for g in gold) for c in CLASSES},
        },
        "filter": {
            "confusion": filter_cm.table(),
            "accuracy": filter_cm.accuracy(),
            "recall": {c: filter_cm.recall(c) for c in CLASSES},
            "promise_passages_routed_to_extraction": (
                routed_promise / gold_promise_passages if gold_promise_passages else None
            ),
        },
        "passage_label_end_to_end": {
            "confusion": e2e_cm.table(),
            "accuracy": e2e_cm.accuracy(),
            "recall": {c: e2e_cm.recall(c) for c in CLASSES},
        },
        "extraction": {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            **scores,
            "ci95": cis,
            "fields": M.field_agreement(all_matches),
        },
        "quote_fidelity": {
            "stored_quotes_verbatim": 1.0 if stored else None,
            "stored_quotes": stored,
            "model_quotes_dropped_after_retry": dropped,
            "model_first_try_verbatim": (stored / (stored + dropped)) if stored + dropped else None,
        },
        "prefilter": {
            "random_non_keyword_rows": len(nonkw),
            "with_a_promise": k_miss,
            "miss_rate_per_passage": miss_rate,
            "miss_rate_ci95": M.wilson(k_miss, len(nonkw)),
            "estimated_recall": est,
            "corpus_counts": corpus_counts,
        },
        "disagreements": disagreements,
    }


def _row(g: GoldPassage, issue: str, gold_quote: str, model_quote: str, extra: dict) -> dict:
    return {
        "passage_id": g.passage_id,
        "ticker": g.ticker,
        "gold_label": g.label,
        "issue": issue,
        "gold_quote": gold_quote,
        "model_quote": model_quote,
        "passage": g.text,
    }


def costs(ledger: Ledger, models: set[str], prompt_ids: set[str]) -> dict[str, str]:
    by_stage: dict[str, Decimal] = defaultdict(Decimal)
    for c in ledger.calls():
        if c.model in models and c.prompt_version in prompt_ids:
            by_stage[c.stage] += c.cost_usd
    return {k: str(v) for k, v in sorted(by_stage.items())}


def fmt(x: float | None, pct: bool = True) -> str:
    if x is None:
        return "n/a"
    return f"{100 * x:.1f}%" if pct else f"{x:.3f}"


def fmt_ci(ci) -> str:
    return f"[{fmt(ci[0])}, {fmt(ci[1])}]" if ci else ""


def render_markdown(result: dict) -> str:
    e = result["extraction"]
    f = result["filter"]
    q = result["quote_fidelity"]
    pf = result["prefilter"]
    g = result["gold"]
    lines = [
        f"# Eval: {result['split']} split, variant {result['variant']}",
        "",
        f"_{result['created']} · git {result['git_sha']} · prompts {', '.join(result['prompts'])}"
        f" · models {', '.join(result['models'])}_",
        "",
        f"Gold: {g['passages']} labeled passages ({g['keyword_passages']} keyword, "
        f"{g['random_non_keyword_passages']} random non-keyword), {g['promises']} promises.",
        "",
        "## Extraction (promise level)",
        "",
        "| Metric | Value | 95% interval |",
        "|---|---|---|",
        f"| Precision | {fmt(e['precision'])} | {fmt_ci(e['ci95']['precision'])} |",
        f"| Recall | {fmt(e['recall'])} | {fmt_ci(e['ci95']['recall'])} |",
        f"| F1 | {fmt(e['f1'])} | {fmt_ci(e['ci95']['f1'])} |",
        f"| Matched / extra / missed | {e['tp']} / {e['fp']} / {e['fn']} | |",
        "",
        "| Field (matched promises) | n | Accuracy |",
        "|---|---|---|",
    ]
    for name, v in e["fields"].items():
        lines.append(f"| {name} | {v['n']} | {fmt(v['accuracy'])} |")
    lines += [
        "",
        "## Filter (keyword passages)",
        "",
        f"Accuracy {fmt(f['accuracy'])}. Gold-promise passages sent on to extraction: "
        f"{fmt(f['promise_passages_routed_to_extraction'])}.",
        "",
        "## Quote fidelity",
        "",
        f"Stored quotes verbatim: {fmt(q['stored_quotes_verbatim'])} ({q['stored_quotes']}). "
        f"Model quotes dropped after one retry: {q['model_quotes_dropped_after_retry']}.",
        "",
        "## Keyword prefilter",
        "",
        f"{pf['with_a_promise']} of {pf['random_non_keyword_rows']} random non-keyword passages "
        f"contained a promise (miss rate {fmt(pf['miss_rate_per_passage'])}, 95% interval "
        f"{fmt_ci(pf['miss_rate_ci95'])}). Estimated prefilter recall: "
        f"{fmt(pf['estimated_recall'])}.",
        "",
        "## Cost",
        "",
        f"Ledger cost of the calls behind these outputs: {result['cost_usd'] or 'none yet'}.",
        "",
        f"Disagreements for review: {len(result['disagreements'])} rows "
        f"({result.get('disagreements_file') or 'not written'}).",
    ]
    return "\n".join(lines) + "\n"


def history_row(result: dict) -> str:
    e = result["extraction"]
    total = sum(Decimal(v) for v in result["cost_usd"].values()) if result["cost_usd"] else None
    promises = result["quote_fidelity"]["stored_quotes"]
    per = f"${total / promises:.4f}" if total is not None and promises else "n/a"
    return (
        f"| {result['created'][:10]} | {result['split']} ({result['gold']['passages']} passages, "
        f"{result['variant']}) | {fmt(e['f1'])} {fmt_ci(e['ci95']['f1'])} | (Phase 3) | "
        f"{fmt(result['quote_fidelity']['stored_quotes_verbatim'])} | {per} |"
    )


def update_readme(readme: Path, row: str) -> None:
    text = readme.read_text(encoding="utf-8")
    if README_START not in text:
        return
    head, rest = text.split(README_START, 1)
    body, tail = rest.split(README_END, 1)
    rows = [r for r in body.strip().splitlines() if r.strip() and "(Phase 2)" not in r]
    rows.append(row)
    readme.write_text(
        head + README_START + "\n" + "\n".join(rows) + "\n" + README_END + tail,
        encoding="utf-8",
        newline="\n",
    )


def write_results(results_dir: Path, result: dict, stamp: str) -> tuple[Path, Path]:
    results_dir.mkdir(parents=True, exist_ok=True)
    jpath = results_dir / f"{stamp}.json"
    mpath = results_dir / f"{stamp}.md"
    slim = {k: v for k, v in result.items() if k != "disagreements"}
    slim["disagreement_count"] = len(result["disagreements"])
    jpath.write_text(json.dumps(slim, indent=2, sort_keys=True, default=str) + "\n",
                     encoding="utf-8", newline="\n")  # fmt: skip
    mpath.write_text(render_markdown(result), encoding="utf-8", newline="\n")
    return jpath, mpath


def timestamp(git_sha: str) -> str:
    return utc_now().replace(":", "").replace("-", "").replace("+0000", "Z")[:15] + f"_{git_sha}"
