"""`aipb import-labels`: check returned packets and write the gold files.

Every problem is reported in plain English with the row number, so the CS student can
forward the report to the finance student as is. Rows with problems are left out of the
gold files (and listed); everything else is imported. Re-running is safe: the gold files
are rebuilt from all returned files each time.

Writes:
- evals/gold/passages.csv   one row per labeled passage (label, notes, how it was sampled)
- evals/gold/promises.csv   one row per promise (verbatim quote, claim type, metric, ...)
- evals/gold/import_report.md
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import load_workbook

from aipb.budget.ledger import utc_now
from aipb.labeling import schema as S
from aipb.parse.passages import normalize_for_match

PASSAGE_COLUMNS = (
    "row_id", "passage_id", "ticker", "form", "filing_date", "section", "sampled_as",
    "label", "notes", "text_sha256", "source_file",
)  # fmt: skip
PROMISE_COLUMNS = (
    "row_id", "passage_id", "ticker", "promise_n", "quote", "claim_type", "metric", "target",
    "deadline",
)  # fmt: skip
_ELLIPSIS = re.compile(r"\.\.\.|\u2026")
_SURROUNDING_QUOTES = "\"'\u201c\u201d\u2018\u2019 "


@dataclass
class Problem:
    row: int | None
    row_id: str
    message: str

    def __str__(self) -> str:
        where = f"Row {self.row}" if self.row else "File"
        rid = f" ({self.row_id})" if self.row_id else ""
        return f"{where}{rid}: {self.message}"


@dataclass
class FileReport:
    file: str
    ticker: str = ""
    rows: int = 0
    labeled: int = 0
    unlabeled: int = 0
    promises: int = 0
    by_label: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    problems: list[Problem] = field(default_factory=list)


def load_keys(gold_dir: Path) -> dict[str, dict]:
    keys: dict[str, dict] = {}
    for path in sorted((gold_dir / "packets" / S.PACKET_VERSION).glob("*_key.csv")):
        with path.open("r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                keys[row["row_id"]] = row
    return keys


def _cell(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _match_label(value: str) -> str | None:
    norm = " ".join(value.lower().split())
    for label in S.LABELS:
        if norm == label.lower():
            return label
    return None


def find_quote(quote: str, passage_text: str) -> str | None:
    """The passage's own wording for `quote` (normalized), or None if it is not there.

    Capitalization differences are forgiven (a labeler often capitalizes the first word),
    but every word must appear in the passage, in order, with nothing in between.
    """
    q = normalize_for_match(quote.strip(_SURROUNDING_QUOTES))
    text = normalize_for_match(passage_text)
    if not q:
        return None
    i = text.find(q)
    if i < 0:
        i = text.lower().find(q.lower())
    return text[i : i + len(q)] if i >= 0 else None


def read_sheet(path: Path) -> tuple[list[tuple[int, dict[str, str]]], list[Problem]]:
    wb = load_workbook(path, data_only=True, read_only=True)
    if "Passages" not in wb.sheetnames:
        return [], [Problem(None, "", "The 'Passages' tab is missing or was renamed.")]
    ws = wb["Passages"]
    rows_iter = ws.iter_rows(values_only=True)
    header = [_cell(h) for h in next(rows_iter, ())]
    by_title = {title.lower(): key for key, title in S.HEADER.items()}
    col = {by_title[h.lower()]: i for i, h in enumerate(header) if h.lower() in by_title}
    missing = [S.HEADER[k] for k in ("row_id", "label", "p1_quote") if k not in col]
    if missing:
        msg = f"These column headers are missing or were renamed: {', '.join(missing)}."
        return [], [Problem(None, "", msg)]
    out = []
    for r, values in enumerate(rows_iter, start=2):
        rec = {k: _cell(values[i]) if i < len(values) else "" for k, i in col.items()}
        if any(rec.values()):
            out.append((r, rec))
    wb.close()
    return out, []


def check_file(path: Path, keys: dict[str, dict]) -> tuple[FileReport, list[dict], list[dict]]:
    rep = FileReport(file=path.name)
    passages: list[dict] = []
    promises: list[dict] = []
    rows, problems = read_sheet(path)
    rep.problems += problems
    first_label: dict[str, str] = {}
    promise_counter: dict[str, int] = defaultdict(int)
    label_editable = (S.LABEL_PROMISE, S.LABEL_UNSURE)

    for r, rec in rows:
        rid = rec.get("row_id", "")
        filled = {k: v for k, v in rec.items() if v and k not in ("row_id", "ticker", "form",
                  "filing_date", "section", "link", "text")}  # fmt: skip
        if not rid:
            if filled:
                rep.problems.append(Problem(r, "", "this row has labels but no Row ID. If you "
                                    "inserted it for an extra promise, copy the Row ID from the "
                                    "row above."))  # fmt: skip
            continue
        key = keys.get(rid)
        if key is None:
            rep.problems.append(Problem(r, rid, "this Row ID is not from any packet. Was the row "
                                "copied from another file, or the ID edited?"))  # fmt: skip
            continue
        if rep.ticker and key["ticker"] != rep.ticker:
            rep.problems.append(Problem(r, rid, f"this row belongs to the {key['ticker']} packet, "
                                f"not {rep.ticker}."))  # fmt: skip
            continue
        rep.ticker = rep.ticker or key["ticker"]

        repeat = rid in first_label
        raw_label = rec.get("label", "")
        label = _match_label(raw_label) if raw_label else None
        if raw_label and label is None:
            rep.problems.append(Problem(r, rid, f"'{raw_label}' is not one of the label choices. "
                                "Pick from the dropdown."))  # fmt: skip
            continue
        if repeat:
            label = label or first_label[rid]
            if label != first_label[rid]:
                rep.problems.append(Problem(r, rid, "this Row ID appears twice with different "
                                    "labels. Use one label per passage."))  # fmt: skip
                continue
            if label not in label_editable:
                msg = f"an extra row is only for a third promise, but the label is '{label}'."
                rep.problems.append(Problem(r, rid, msg))
                continue
        else:
            rep.rows += 1
            if label is None:
                if filled:
                    rep.problems.append(Problem(r, rid, "promise or notes are filled in but "
                                        "'Your label' is empty."))  # fmt: skip
                else:
                    rep.unlabeled += 1
                continue
            first_label[rid] = label

        row_promises, row_problems = _check_promises(r, rid, rec, label, key)
        if row_problems:
            rep.problems += row_problems
            if not repeat:
                del first_label[rid]
            continue
        if not repeat:
            rep.labeled += 1
            rep.by_label[label] += 1
            passages.append(
                {
                    "row_id": rid, "passage_id": key["passage_id"], "ticker": key["ticker"],
                    "form": key["form"], "filing_date": key["filing_date"],
                    "section": key["section"], "sampled_as": key["sampled_as"], "label": label,
                    "notes": rec.get("notes", ""), "text_sha256": key["text_sha256"],
                    "source_file": path.name,
                }
            )  # fmt: skip
        for p in row_promises:
            promise_counter[rid] += 1
            p["promise_n"] = promise_counter[rid]
            promises.append(p)
            rep.promises += 1
    return rep, passages, promises


def _check_promises(
    r: int, rid: str, rec: dict[str, str], label: str, key: dict
) -> tuple[list[dict], list[Problem]]:
    problems: list[Problem] = []
    found: list[dict] = []
    for n in range(1, S.N_PROMISE_SLOTS + 1):
        slot = {f: rec.get(f"p{n}_{f}", "") for f in S.PROMISE_FIELDS}
        if not any(slot.values()):
            continue
        if label in (S.LABEL_NONE, S.LABEL_HYPE):
            problems.append(Problem(r, rid, f"the label is '{label}' but Promise {n} is filled "
                            f"in. Clear Promise {n}, or change the label to "
                            f"'{S.LABEL_PROMISE}'."))  # fmt: skip
            continue
        if not slot["quote"]:
            problems.append(Problem(r, rid, f"Promise {n} has details but no quote. Copy the "
                            "promise's exact words from the passage."))  # fmt: skip
            continue
        if _ELLIPSIS.search(slot["quote"]):
            problems.append(Problem(r, rid, f"Promise {n}'s quote contains '...'. Copy one "
                            "continuous piece of text instead (part of a sentence is "
                            "fine)."))  # fmt: skip
            continue
        exact = find_quote(slot["quote"], key["text"])
        if exact is None:
            problems.append(Problem(r, rid, f"Promise {n}'s quote is not in the passage text. "
                            "Copy it exactly from the Passage column; don't retype or "
                            "paraphrase it."))  # fmt: skip
            continue
        if slot["claim_type"] not in S.CLAIM_TYPES:
            what = f"'{slot['claim_type']}' is not a claim type" if slot["claim_type"] else (
                "the claim type is empty")  # fmt: skip
            problems.append(Problem(r, rid, f"Promise {n}: {what}. Pick one from the "
                            "dropdown."))  # fmt: skip
            continue
        found.append(
            {
                "row_id": rid, "passage_id": key["passage_id"], "ticker": key["ticker"],
                "quote": exact, "claim_type": slot["claim_type"], "metric": slot["metric"],
                "target": slot["target"], "deadline": slot["deadline"],
            }
        )  # fmt: skip
    if label == S.LABEL_PROMISE and not found and not problems:
        msg = (f"the label is '{S.LABEL_PROMISE}' but Promise 1 is empty. Copy the promise's "
               "exact words into 'Promise 1: quote'.")  # fmt: skip
        problems.append(Problem(r, rid, msg))
    if label == S.LABEL_UNSURE:
        found = []  # unsure rows are kept for review but never used as gold promises
    return found, problems


def _write_csv(path: Path, columns: tuple[str, ...], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow({c: row.get(c, "") for c in columns})


def render_report(reports: list[FileReport], n_passages: int, n_promises: int) -> str:
    lines = [
        "# Label import report",
        "",
        f"_Generated {utc_now()} by `aipb import-labels`._",
        "",
        f"Imported **{n_passages} labeled passages** and **{n_promises} promises** from "
        f"{len(reports)} file(s).",
        "",
        "| File | Company | Rows | Labeled | Not labeled yet | Promises | Problems |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in reports:
        lines.append(
            f"| {r.file} | {r.ticker or '?'} | {r.rows} | {r.labeled} | {r.unlabeled} | "
            f"{r.promises} | {len(r.problems)} |"
        )
    problem_files = [r for r in reports if r.problems]
    lines += ["", "## Problems to fix" if problem_files else "## No problems found", ""]
    if not problem_files:
        lines.append("Every labeled row passed the checks.")
    for r in problem_files:
        lines += [f"### {r.file}", "",
                  "These rows were left out of the gold files. Fix them in the spreadsheet "
                  "and return it again; the other rows are already imported.", ""]  # fmt: skip
        lines += [f"- {p}" for p in r.problems]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def import_labels(returned_dir: Path, gold_dir: Path) -> list[FileReport]:
    keys = load_keys(gold_dir)
    reports: list[FileReport] = []
    all_passages: list[dict] = []
    all_promises: list[dict] = []
    seen_tickers: dict[str, str] = {}
    files = sorted(p for p in returned_dir.glob("*.xlsx") if not p.name.startswith("~$"))
    for path in files:
        rep, passages, promises = check_file(path, keys)
        if not keys:
            rep.problems.append(Problem(None, "", "No packet keys found in evals/gold/packets. "
                                "Run aipb packets first."))  # fmt: skip
        if rep.ticker and rep.ticker in seen_tickers:
            rep.problems.append(Problem(None, "", f"{seen_tickers[rep.ticker]} already has the "
                                f"{rep.ticker} labels. Keep only one returned file per "
                                "company; this one was skipped."))  # fmt: skip
            passages, promises = [], []
            rep.labeled = rep.promises = 0
        elif rep.ticker:
            seen_tickers[rep.ticker] = path.name
        reports.append(rep)
        all_passages += passages
        all_promises += promises
    all_passages.sort(key=lambda x: x["row_id"])
    all_promises.sort(key=lambda x: (x["row_id"], x["promise_n"]))
    _write_csv(gold_dir / "passages.csv", PASSAGE_COLUMNS, all_passages)
    _write_csv(gold_dir / "promises.csv", PROMISE_COLUMNS, all_promises)
    (gold_dir / "import_report.md").write_text(
        render_report(reports, len(all_passages), len(all_promises)),
        encoding="utf-8",
        newline="\n",
    )
    return reports
