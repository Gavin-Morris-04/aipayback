"""`aipb packets`: Excel labeling packets for the finance student, one file per company.

Rows come from the KEYWORD prefilter, never from model output, so the gold labels are not
biased toward what the model finds. About 5% of rows are random passages with no keyword
hit; their labels measure how many AI promises the keyword filter misses (prefilter recall).

Only promise-window filings (2024-01-01 to 2025-12-31) are sampled, only canonical
passages (boilerplate duplicates removed), and the sample is seeded so it is reproducible.

Outputs:
- exports/packets/<TICKER>_packet_v1.xlsx  (git-ignored; shared through Google Drive)
- evals/gold/packets/v1/<TICKER>_key.csv    (committed: row_id -> passage_id, text hash,
  and whether the row was a keyword or a random non-keyword sample)
- evals/gold/packets/v1/manifest.json       (committed: seed, versions, counts)
"""

from __future__ import annotations

import csv
import json
import random
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from openpyxl import Workbook
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from aipb.budget.ledger import utc_now
from aipb.labeling import schema as S
from aipb.parse.html import PARSER_VERSION
from aipb.stages.prefilter import Lexicon

MIN_WORDS = 40
# The key stores the passage text too, so imports and evals never depend on the local
# database or on the parser version that produced the packet.
KEY_COLUMNS = (
    "row_id", "passage_id", "ticker", "form", "filing_date", "section", "sampled_as",
    "text_sha256", "url", "text",
)  # fmt: skip
_RED_BOLD = InlineFont(b=True, color="C00000")
_HEADER_FILL = PatternFill("solid", fgColor="1F3864")
_LABEL_FILL = PatternFill("solid", fgColor="FFF2CC")


class PacketsExist(RuntimeError):
    """Refuse to overwrite packet keys that returned labels may depend on."""


@dataclass(frozen=True)
class Row:
    row_id: str
    passage_id: str
    ticker: str
    form: str
    filing_date: str
    section: str
    url: str
    text: str
    text_sha256: str
    sampled_as: str  # "keyword" or "non_keyword"


def allocate(pools: dict[str, int], total: int) -> dict[str, int]:
    """Water-filling: every company gets min(pool, cap), with one cap chosen to fit `total`."""
    alloc = dict.fromkeys(pools, 0)
    remaining = dict(pools)
    left = total
    while left > 0 and any(remaining.values()):
        open_ = [t for t, n in remaining.items() if n > 0]
        share = max(1, left // len(open_))
        for t in sorted(open_, key=lambda t: remaining[t]):
            take = min(share, remaining[t], left)
            alloc[t] += take
            remaining[t] -= take
            left -= take
            if left == 0:
                break
    return alloc


def _candidates(conn: sqlite3.Connection, cik: int, keyword: bool) -> list[sqlite3.Row]:
    kw_clause = "p.kw_hits != '[]'" if keyword else "p.kw_hits = '[]'"
    return conn.execute(
        f"""
        SELECT p.passage_id, p.form, p.filing_date, p.section, p.seq, p.text, p.text_sha256,
               d.url
        FROM passages p
        LEFT JOIN filing_docs d ON d.accession = p.accession AND d.role = p.doc_role
        WHERE p.cik = ? AND p.dup_of IS NULL AND p.kw_hits IS NOT NULL AND {kw_clause}
          AND p.filing_date BETWEEN ? AND ? AND p.words >= ?
        ORDER BY p.passage_id
        """,
        (cik, *S.PROMISE_WINDOW, MIN_WORDS),
    ).fetchall()


def select_rows(
    conn: sqlite3.Connection,
    companies: dict[str, int],
    *,
    total: int = 450,
    non_keyword_share: float = 0.05,
    seed: int = S.SAMPLE_SEED,
) -> dict[str, list[Row]]:
    kw_pool = {t: _candidates(conn, cik, True) for t, cik in companies.items()}
    non_pool = {t: _candidates(conn, cik, False) for t, cik in companies.items()}
    n_non = round(total * non_keyword_share)
    kw_alloc = allocate({t: len(v) for t, v in kw_pool.items()}, total - n_non)
    non_alloc = allocate({t: len(v) for t, v in non_pool.items()}, n_non)

    out: dict[str, list[Row]] = {}
    for ticker in sorted(companies):
        # One seeded stream per company: changing the company list does not reshuffle the
        # rows of companies that stay (unless their share of the total changes).
        rng = random.Random(f"{seed}-{ticker}")
        picked = [(r, "keyword") for r in rng.sample(kw_pool[ticker], kw_alloc[ticker])]
        picked += [(r, "non_keyword") for r in rng.sample(non_pool[ticker], non_alloc[ticker])]
        # Read in filing order, so keyword and random rows are mixed together.
        picked.sort(key=lambda x: (x[0]["filing_date"], x[0]["passage_id"]))
        out[ticker] = [
            Row(
                row_id=f"{ticker}-{i:03d}",
                passage_id=r["passage_id"],
                ticker=ticker,
                form=r["form"],
                filing_date=r["filing_date"],
                section=r["section"],
                url=r["url"] or "",
                text=r["text"],
                text_sha256=r["text_sha256"],
                sampled_as=kind,
            )
            for i, (r, kind) in enumerate(picked, start=1)
        ]
    return out


def highlight(text: str, lexicon: Lexicon) -> CellRichText | str:
    spans: list[tuple[int, int]] = []
    for pat in lexicon.ai:
        spans += [m.span() for m in pat.finditer(text)]
    if not spans:
        return text
    spans.sort()
    merged: list[list[int]] = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    parts: list = []
    pos = 0
    for a, b in merged:
        if a > pos:
            parts.append(text[pos:a])
        parts.append(TextBlock(_RED_BOLD, text[a:b]))
        pos = b
    if pos < len(text):
        parts.append(text[pos:])
    return CellRichText(parts)


INSTRUCTIONS = [
    ("AIPayback labeling packet", ""),
    ("Packet", "{packet}"),
    ("Company", "{ticker}"),
    ("Rows", "{rows}"),
    ("", ""),
    ("What to do", "Read each passage in the Passages tab and pick one label in the yellow "
     "'Your label' column. Full guide with examples: docs/finance/LABELING_GUIDE.md."),
    (S.LABEL_PROMISE, "A forward-looking AI statement specific enough that a later filing could "
     "confirm or refute it (a number, a date, or a concrete deliverable). Copy the exact words "
     "into 'Promise 1: quote' and fill in claim type, metric, target and deadline."),
    (S.LABEL_HYPE, "Forward-looking AI talk with nothing checkable in it."),
    (S.LABEL_NONE, "No forward-looking AI statement (past results, risk boilerplate, or not AI)."),
    (S.LABEL_UNSURE, "Use this freely, and say why in Notes."),
    ("Quotes", "Copy one continuous piece of text from the passage, exactly as written. "
     "No '...' and no paraphrasing. Part of a sentence is fine."),
    ("Two promises?", "Use the Promise 2 columns. Three or more: copy the whole row, insert it "
     "below, keep the same Row ID, and fill in the extra promise."),
    ("Claim types", ", ".join(S.CLAIM_TYPES)),
    ("When done", "Save and put the file in the Drive folder 'returned'. Keep the file name."),
]  # fmt: skip


def write_workbook(path: Path, ticker: str, rows: list[Row], lexicon: Lexicon) -> None:
    wb = Workbook()
    info = wb.active
    info.title = "Instructions"
    packet = f"{ticker}_{S.PACKET_VERSION}"
    for r, (k, v) in enumerate(INSTRUCTIONS, start=1):
        info.cell(r, 1, k).font = Font(bold=True)
        info.cell(r, 2, v.format(packet=packet, ticker=ticker, rows=len(rows)))
        info.cell(r, 2).alignment = Alignment(wrap_text=True, vertical="top")
    info.column_dimensions["A"].width = 32
    info.column_dimensions["B"].width = 110

    ws = wb.create_sheet("Passages")
    keys = [k for k, _, _ in S.COLUMNS]
    for c, (_, title, width) in enumerate(S.COLUMNS, start=1):
        cell = ws.cell(1, c, title)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = _HEADER_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[cell.column_letter].width = width
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = "B2"

    col = {k: i for i, k in enumerate(keys, start=1)}
    for r, row in enumerate(rows, start=2):
        values = {
            "row_id": row.row_id,
            "ticker": row.ticker,
            "form": row.form,
            "filing_date": row.filing_date,
            "section": S.section_name(row.section),
        }
        for k, v in values.items():
            ws.cell(r, col[k], v).alignment = Alignment(vertical="top", wrap_text=True)
        link = ws.cell(r, col["link"], "Open filing" if row.url else "")
        if row.url:
            link.hyperlink = row.url
            link.font = Font(color="0563C1", underline="single")
        link.alignment = Alignment(vertical="top")
        text_cell = ws.cell(r, col["text"])
        text_cell.value = highlight(row.text, lexicon)
        text_cell.alignment = Alignment(wrap_text=True, vertical="top")
        for k in keys[keys.index("label") :]:
            cell = ws.cell(r, col[k])
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            if k == "label":
                cell.fill = _LABEL_FILL
        lines = max(3, len(row.text) // 115 + row.text.count("\n") + 1)
        ws.row_dimensions[r].height = min(409, 15 * lines)

    last = len(rows) + 200  # room for inserted rows
    label_dv = DataValidation(
        type="list", formula1='"' + ",".join(S.LABELS) + '"', allow_blank=True
    )
    label_dv.error = "Pick one of the four labels from the list."
    label_dv.errorTitle = "Label"
    ws.add_data_validation(label_dv)
    label_dv.add(f"{ws.cell(2, col['label']).column_letter}2:"
                 f"{ws.cell(2, col['label']).column_letter}{last}")  # fmt: skip
    claim_dv = DataValidation(
        type="list", formula1='"' + ",".join(S.CLAIM_TYPES) + '"', allow_blank=True
    )
    claim_dv.error = "Pick a claim type from the list."
    ws.add_data_validation(claim_dv)
    for n in range(1, S.N_PROMISE_SLOTS + 1):
        letter = ws.cell(2, col[f"p{n}_claim_type"]).column_letter
        claim_dv.add(f"{letter}2:{letter}{last}")
    ws.auto_filter.ref = f"A1:{ws.cell(1, len(keys)).column_letter}{len(rows) + 1}"
    wb.active = 1
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def write_key(path: Path, rows: list[Row]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(KEY_COLUMNS)
        for r in rows:
            w.writerow(
                [r.row_id, r.passage_id, r.ticker, r.form, r.filing_date, r.section,
                 r.sampled_as, r.text_sha256, r.url, r.text]
            )  # fmt: skip


def build_packets(
    conn: sqlite3.Connection,
    companies: dict[str, int],
    lexicon: Lexicon,
    *,
    exports_dir: Path,
    gold_dir: Path,
    total: int = 450,
    non_keyword_share: float = 0.05,
    force: bool = False,
) -> dict[str, list[Row]]:
    key_dir = gold_dir / "packets" / S.PACKET_VERSION
    existing = sorted(key_dir.glob("*_key.csv"))
    if existing and not force:
        raise PacketsExist(
            f"Packets {S.PACKET_VERSION} already exist ({len(existing)} key files in {key_dir}). "
            "Returned labels are matched through these keys, so overwriting them can orphan "
            "labeling work. If labeling has started, bump PACKET_VERSION in "
            "src/aipb/labeling/schema.py instead. Otherwise re-run with --force."
        )
    for old in existing:  # --force: drop keys of companies no longer in the list
        old.unlink()
    for old in (exports_dir / "packets").glob(f"*_packet_{S.PACKET_VERSION}.xlsx"):
        old.unlink()
    selected = select_rows(conn, companies, total=total, non_keyword_share=non_keyword_share)
    for ticker, rows in selected.items():
        write_workbook(
            exports_dir / "packets" / f"{ticker}_packet_{S.PACKET_VERSION}.xlsx", ticker, rows,
            lexicon,
        )  # fmt: skip
        write_key(key_dir / f"{ticker}_key.csv", rows)
    meta = {
        "packet_version": S.PACKET_VERSION,
        "created": utc_now(),
        "seed": S.SAMPLE_SEED,
        "promise_window": list(S.PROMISE_WINDOW),
        "parser_version": PARSER_VERSION,
        "keyword_version": lexicon.version,
        "target_rows": total,
        "non_keyword_share": non_keyword_share,
        "rows": {t: len(r) for t, r in selected.items()},
        "keyword_rows": {t: sum(x.sampled_as == "keyword" for x in r) for t, r in selected.items()},
    }
    (key_dir / "manifest.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return selected
