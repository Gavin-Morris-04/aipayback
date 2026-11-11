"""Disagreement workbook: every row where the model and Nick's labels differ, for review.

Nick marks each row "Model wrong", "Label wrong" or "Rubric unclear". Those verdicts
decide what changes next: the prompt, the gold label, or the rubric.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

VERDICTS = ("Model wrong", "Label wrong", "Rubric unclear")
COLUMNS = (
    ("passage_id", "Passage ID", 22),
    ("ticker", "Company", 9),
    ("gold_label", "Your label", 12),
    ("issue", "What differs", 28),
    ("gold_quote", "Your quote", 40),
    ("model_quote", "Model's quote", 40),
    ("passage", "Passage", 90),
    ("verdict", "Verdict", 16),
    ("notes", "Notes", 30),
)


def write_disagreements(path: Path, rows: list[dict], title: str) -> Path:
    wb = Workbook()
    info = wb.active
    info.title = "Instructions"
    for r, (k, v) in enumerate(
        [
            ("Disagreement review", title),
            (
                "What to do",
                "For each row, pick a Verdict: 'Model wrong' (your label is right), "
                "'Label wrong' (the model is right; we'll fix the gold label), or 'Rubric "
                "unclear' (the rules don't decide it; say why in Notes).",
            ),
            ("Return", "Save and put the file in the Drive folder 'returned'."),
        ],
        start=1,
    ):
        info.cell(r, 1, k).font = Font(bold=True)
        info.cell(r, 2, v).alignment = Alignment(wrap_text=True)
    info.column_dimensions["A"].width = 22
    info.column_dimensions["B"].width = 100

    ws = wb.create_sheet("Disagreements")
    for c, (_, head, width) in enumerate(COLUMNS, start=1):
        cell = ws.cell(1, c, head)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F3864")
        ws.column_dimensions[cell.column_letter].width = width
    ws.freeze_panes = "B2"
    for r, row in enumerate(rows, start=2):
        for c, (key, _, _) in enumerate(COLUMNS, start=1):
            cell = ws.cell(r, c, row.get(key, ""))
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[r].height = min(409, 15 * max(3, len(row.get("passage", "")) // 100))
    letter = ws.cell(1, len(COLUMNS) - 1).column_letter
    dv = DataValidation(type="list", formula1='"' + ",".join(VERDICTS) + '"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"{letter}2:{letter}{len(rows) + 100}")
    wb.active = 1
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
