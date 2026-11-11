"""Status labeling (Phase 3): Nick labels 40-60 promises' statuses in one Excel file.

Each row shows the promise and the SAME code-retrieved evidence and reported numbers the
judge sees, but never the model's verdict, so the labels stay independent. Nick can open
any filing from the SEC links. The key (committed) stores the promise's passage id and
quote, so gold statuses can be matched to clusters even if cluster ids change later.
"""

from __future__ import annotations

import csv
import json
import random
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from aipb.budget.ledger import utc_now
from aipb.verify.numbers import NumberRow, deadline_end, fiscal_year_end

VERSION = "v1"
SEED = 20261111
STATUS_LABELS = (
    "Delivered",
    "On track",
    "No evidence yet",
    "Walked back",
    "Walked back (silent)",
    "Unsure",
)
LABEL_TO_CODE = {
    "Delivered": ("delivered", False),
    "On track": ("on_track", False),
    "No evidence yet": ("no_evidence_yet", False),
    "Walked back": ("walked_back", False),
    "Walked back (silent)": ("walked_back", True),
}
COLUMNS = (
    ("row_id", "Row ID", 9),
    ("ticker", "Company", 9),
    ("first_stated", "First stated", 12),
    ("quote", "Promise (verbatim)", 50),
    ("fields", "Target / deadline", 26),
    ("deadline_end", "Deadline period ends", 14),
    ("evidence", "Later filings (search results)", 90),
    ("numbers", "Reported numbers (XBRL, computed by code)", 50),
    ("link", "Promise filing", 12),
    ("status", "Your status", 20),
    ("used", "Evidence you relied on", 26),
    ("notes", "Notes", 30),
)
KEY_COLUMNS = ("row_id", "cluster_id", "ticker", "passage_id", "quote", "first_stated")


@dataclass
class StatusImport:
    rows: int = 0
    labeled: int = 0
    problems: list[str] = field(default_factory=list)


def build(
    conn: sqlite3.Connection,
    out_xlsx: Path,
    key_dir: Path,
    *,
    n: int = 60,
    variant: str = "default",
) -> int:
    clusters = conn.execute(
        "SELECT k.*, c.ticker FROM promise_clusters k JOIN companies c ON c.cik=k.cik "
        "WHERE k.variant=? ORDER BY k.cluster_id",
        (variant,),
    ).fetchall()
    by_co: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for c in clusters:
        by_co[c["ticker"]].append(c)
    rng = random.Random(SEED)
    picked: list[sqlite3.Row] = []
    pools = {t: rng.sample(v, len(v)) for t, v in sorted(by_co.items())}
    while len(picked) < n and any(pools.values()):  # round-robin across companies
        for t in sorted(pools):
            if pools[t] and len(picked) < n:
                picked.append(pools[t].pop())
    picked.sort(key=lambda c: (c["ticker"], c["first_stated"], c["cluster_id"]))

    wb = Workbook()
    info = wb.active
    info.title = "Instructions"
    for r, (k, v) in enumerate(
        [
            ("Status labeling", f"{len(picked)} promises. About 5-8 minutes each."),
            (
                "What to do",
                "For each promise, read the later-filing excerpts and the reported "
                "numbers, open the filings if needed, and pick a status using your "
                "rubric (sections 4 and 5) and evidence map. Choose Unsure freely.",
            ),
            (
                "Held as pending",
                "If your rubric says a promise must be held as 'Status pending review' "
                "(a vague specificity-1 deliverable, unclear run-rate vs realized, a "
                "changed GAAP/non-GAAP basis or definition, or a percentage target with "
                "no stated base), choose Unsure and name the rule in Notes.",
            ),
            (
                "Evidence you relied on",
                "Write the E-numbers or N-numbers you used, or a short "
                "note like '2025 10-K, MD&A'.",
            ),
            ("Return", "Save and put the file in the Drive folder 'returned'."),
        ],
        start=1,
    ):
        info.cell(r, 1, k).font = Font(bold=True)
        info.cell(r, 2, v).alignment = Alignment(wrap_text=True)
    info.column_dimensions["A"].width = 24
    info.column_dimensions["B"].width = 100
    ws = wb.create_sheet("Promises")
    for c, (_, head, width) in enumerate(COLUMNS, start=1):
        cell = ws.cell(1, c, head)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F3864")
        cell.alignment = Alignment(wrap_text=True)
        ws.column_dimensions[cell.column_letter].width = width
    ws.freeze_panes = "B2"
    keys = []
    for i, cl in enumerate(picked, start=1):
        rid = f"S-{i:03d}"
        p = conn.execute(
            "SELECT * FROM promises WHERE promise_id=?", (cl["canonical_promise_id"],)
        ).fetchone()
        ev = conn.execute(
            "SELECT e.eid, e.form, e.filing_date, p.text FROM evidence e JOIN passages p "
            "ON p.passage_id=e.passage_id WHERE e.cluster_id=? AND e.variant=? AND "
            "e.source='retrieval' ORDER BY e.eid",
            (cl["cluster_id"], variant),
        ).fetchall()
        nums = conn.execute(
            "SELECT * FROM numbers WHERE cluster_id=? AND variant=? ORDER BY nid",
            (cl["cluster_id"], variant),
        ).fetchall()
        link = conn.execute(
            "SELECT d.url FROM filing_docs d JOIN passages s ON s.accession=d.accession "
            "AND s.doc_role=d.role WHERE s.passage_id=?",
            (p["passage_id"],),
        ).fetchone()
        d_end = deadline_end(p["deadline_year"], fiscal_year_end(conn, cl["cik"]))
        fields = (p["metric"], p["target_text"], p["deadline_text"])
        excerpts = [
            f"[{e['eid']}] {e['form']} filed {e['filing_date']}: {e['text'][:700]}" for e in ev
        ]
        values = {
            "row_id": rid,
            "ticker": cl["ticker"],
            "first_stated": cl["first_stated"],
            "quote": p["quote"],
            "fields": "; ".join(x for x in fields if x),
            "deadline_end": d_end or "none stated",
            "evidence": "\n\n".join(excerpts) or "(no matches)",
            "numbers": "\n".join(_number_line(r) for r in nums) or "(none for this claim type)",
        }
        for c, (k, _, _) in enumerate(COLUMNS, start=1):
            cell = ws.cell(i + 1, c, values.get(k, ""))
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        if link:
            lc = ws.cell(i + 1, [k for k, _, _ in COLUMNS].index("link") + 1, "Open filing")
            lc.hyperlink = link[0]
            lc.font = Font(color="0563C1", underline="single")
        ws.cell(i + 1, [k for k, _, _ in COLUMNS].index("status") + 1).fill = PatternFill(
            "solid", fgColor="FFF2CC"
        )
        ws.row_dimensions[i + 1].height = 300
        keys.append(
            {
                "row_id": rid,
                "cluster_id": cl["cluster_id"],
                "ticker": cl["ticker"],
                "passage_id": p["passage_id"],
                "quote": p["quote"],
                "first_stated": cl["first_stated"],
            }
        )
    col = ws.cell(1, [k for k, _, _ in COLUMNS].index("status") + 1).column_letter
    dv = DataValidation(type="list", formula1='"' + ",".join(STATUS_LABELS) + '"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"{col}2:{col}{len(picked) + 50}")
    wb.active = 1
    out_xlsx.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out_xlsx)
    key_dir.mkdir(parents=True, exist_ok=True)
    with (key_dir / "key.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=KEY_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(keys)
    (key_dir / "manifest.json").write_text(
        json.dumps(
            {"version": VERSION, "seed": SEED, "rows": len(picked), "created": utc_now()}, indent=2
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return len(picked)


def _number_line(r: sqlite3.Row) -> str:
    keys = (
        "nid",
        "label",
        "value",
        "unit",
        "kind",
        "tag",
        "fiscal_year",
        "period_start",
        "period_end",
        "accession",
        "filed",
    )
    row = NumberRow(*[r[k] for k in keys])
    return f"{row.nid}: {row.label}: {row.display()}"


def import_statuses(returned: Path, key_dir: Path, gold_csv: Path) -> StatusImport:
    keys = {}
    with (key_dir / "key.csv").open(encoding="utf-8", newline="") as fh:
        keys = {r["row_id"]: r for r in csv.DictReader(fh)}
    rep = StatusImport()
    out = []
    wb = load_workbook(returned, data_only=True, read_only=True)
    if "Promises" not in wb.sheetnames:
        rep.problems.append("The 'Promises' tab is missing or was renamed.")
        return rep
    rows = wb["Promises"].iter_rows(values_only=True)
    header = [str(h or "").strip() for h in next(rows, ())]
    titles = {t: k for k, t, _ in COLUMNS}
    col = {titles[h]: i for i, h in enumerate(header) if h in titles}
    for r, values in enumerate(rows, start=2):
        rid = str(values[col["row_id"]] or "").strip()
        if not rid:
            continue
        rep.rows += 1
        status = str(values[col["status"]] or "").strip()
        if rid not in keys:
            rep.problems.append(f"Row {r} ({rid}): this Row ID is not from the status packet.")
            continue
        if not status:
            continue
        if status not in STATUS_LABELS:
            rep.problems.append(f"Row {r} ({rid}): '{status}' is not one of the status choices.")
            continue
        rep.labeled += 1
        k = keys[rid]
        out.append(
            {
                **k,
                "status": status,
                "used": str(values[col["used"]] or ""),
                "notes": str(values[col["notes"]] or ""),
            }
        )
    wb.close()
    gold_csv.parent.mkdir(parents=True, exist_ok=True)
    with gold_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh, fieldnames=[*KEY_COLUMNS, "status", "used", "notes"], lineterminator="\n"
        )
        w.writeheader()
        w.writerows(out)
    return rep
