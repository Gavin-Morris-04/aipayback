"""Packets -> a labeler fills them in Excel -> import-labels -> gold CSVs.

The "labeler" here is openpyxl writing cells the way the finance student would, including
the mistakes the importer must explain in plain English.
"""

import csv
import shutil

import pytest
from openpyxl import load_workbook
from openpyxl.cell.rich_text import CellRichText
from typer.testing import CliRunner

from aipb import cli
from aipb.labeling import schema as S

runner = CliRunner()


def run(*args, code=0):
    result = runner.invoke(cli.app, list(args))
    assert result.exit_code == code, result.output
    return result


@pytest.fixture
def packet(project):
    for cmd in ("ingest", "parse", "prefilter"):
        run(cmd, "-u", "test")
    run("packets", "-u", "test", "--total", "40", "--non-keyword-share", "0.2")
    return project / "exports" / "packets" / "EXMP_packet_v1.xlsx"


def columns(ws):
    by_title = {c.value: c.column for c in ws[1]}
    return {key: by_title[title] for key, title in S.HEADER.items()}


def find_row(ws, col, needle):
    for r in range(2, ws.max_row + 1):
        if needle in str(ws.cell(r, col["text"]).value or ""):
            return r
    raise AssertionError(f"no row contains {needle!r}")


def fill(ws, col, r, **values):
    for k, v in values.items():
        ws.cell(r, col[k], v)


def returned(project, wb, name="EXMP_packet_v1.xlsx"):
    folder = project / "evals" / "gold" / "returned"
    folder.mkdir(parents=True, exist_ok=True)
    wb.save(folder / name)
    return folder / name


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_packet_layout(packet, project):
    wb = load_workbook(packet, rich_text=True)
    assert wb.sheetnames == ["Instructions", "Passages"]
    ws = wb["Passages"]
    col = columns(ws)
    assert ws.freeze_panes == "B2"
    formulas = {dv.formula1 for dv in ws.data_validations.dataValidation}
    assert '"' + ",".join(S.LABELS) + '"' in formulas
    assert '"' + ",".join(S.CLAIM_TYPES) + '"' in formulas
    r = find_row(ws, col, "run-rate cost savings")
    assert isinstance(ws.cell(r, col["text"]).value, CellRichText)  # AI words highlighted
    assert ws.cell(r, col["link"]).hyperlink.target.startswith("https://www.sec.gov/Archives/")

    keys = read_csv(project / "evals" / "gold" / "packets" / "v1" / "EXMP_key.csv")
    kinds = {k["sampled_as"] for k in keys}
    assert kinds == {"keyword", "non_keyword"}
    assert all(k["filing_date"] <= "2025-12-31" for k in keys)
    # Duplicates are never sampled: the second 10-Q repeats the first word for word.
    assert not any("9999999999-25-000030" in k["passage_id"] for k in keys)


def test_clean_import_writes_gold_files(packet, project):
    wb = load_workbook(packet)
    ws = wb["Passages"]
    col = columns(ws)
    r = find_row(ws, col, "run-rate cost savings")
    fill(
        ws, col, r,
        label="Checkable promise",
        p1_quote="We expect the program to deliver $150 million in annual run-rate cost "
        "savings by the end of 2025",
        p1_claim_type="cost_savings", p1_metric="annual run-rate cost savings",
        p1_target="$150 million", p1_deadline="end of 2025",
        # Capitalized by the labeler; the source says "we plan ...".
        p2_quote="We plan to reduce support headcount by about 10 percent",
        p2_claim_type="workforce", p2_target="10 percent",
    )  # fmt: skip
    # A third promise on an inserted row with the same Row ID.
    extra = ws.max_row + 1
    fill(ws, col, extra, row_id=ws.cell(r, col["row_id"]).value,
         p1_quote="through attrition over the same period", p1_claim_type="workforce")  # fmt: skip
    hype = find_row(ws, col, "generative AI investments")
    fill(ws, col, hype, label="vague ai talk (HYPE)")  # case and spacing are forgiven
    other = find_row(ws, col, "skilled engineers")
    fill(ws, col, other, label="No forward-looking AI statement", notes="supply chain")
    returned(project, wb)

    out = run("import-labels").output
    assert "All rows passed" in out
    gold = project / "evals" / "gold"
    passages = read_csv(gold / "passages.csv")
    promises = read_csv(gold / "promises.csv")
    assert {p["label"] for p in passages} == {
        "Checkable promise", "Vague AI talk (hype)", "No forward-looking AI statement"
    }  # fmt: skip
    assert [p["promise_n"] for p in promises] == ["1", "2", "3"]
    assert promises[1]["quote"] == "we plan to reduce support headcount by about 10 percent"
    assert {p["claim_type"] for p in promises} == {"cost_savings", "workforce"}
    report = (gold / "import_report.md").read_text(encoding="utf-8")
    assert "No problems found" in report


def test_mistakes_are_explained_and_good_rows_still_import(packet, project):
    wb = load_workbook(packet)
    ws = wb["Passages"]
    col = columns(ws)
    good = 2  # the first row; none of the rows below
    fill(ws, col, good, label="Unsure", notes="not sure this is AI")
    mdna = find_row(ws, col, "run-rate cost savings")
    fill(ws, col, mdna, label="Checkable promise", p1_claim_type="cost_savings",
         p1_quote="We expect the program to deliver ... savings")  # fmt: skip
    hype = find_row(ws, col, "generative AI investments")
    fill(ws, col, hype, label="Checkable promise",
         p1_quote="AI investments will transform everything", p1_claim_type="other")  # fmt: skip
    risk = find_row(ws, col, "skilled engineers")
    fill(ws, col, risk, label="promise")
    q = find_row(ws, col, "remains on track")
    fill(ws, col, q, label="Checkable promise")
    ex13 = find_row(ws, col, "25 percent of total revenue")
    fill(ws, col, ex13, label="No forward-looking AI statement",
         p1_quote="more than 25 percent of total revenue by 2026")  # fmt: skip
    ex99 = find_row(ws, col, "double in 2025")
    fill(ws, col, ex99, label="Checkable promise",
         p1_quote="We now expect AI-related software revenue to double in 2025")  # fmt: skip
    fill(ws, col, ws.max_row + 1, row_id="ZZZ-001", label="Unsure")
    returned(project, wb)

    result = run("import-labels", code=1)
    assert "Some rows need fixing" in result.output
    report = (project / "evals" / "gold" / "import_report.md").read_text(encoding="utf-8")
    assert f"Row {mdna}" in report and "contains '...'" in report
    assert f"Row {hype}" in report and "is not in the passage text" in report
    assert f"Row {risk}" in report and "'promise' is not one of the label choices" in report
    assert f"Row {q}" in report and "Promise 1 is empty" in report
    assert f"Row {ex13}" in report and "Clear Promise 1" in report
    assert f"Row {ex99}" in report and "the claim type is empty" in report
    assert "ZZZ-001" in report and "not from any packet" in report
    passages = read_csv(project / "evals" / "gold" / "passages.csv")
    assert [p["label"] for p in passages] == ["Unsure"]  # the one good row is imported
    assert read_csv(project / "evals" / "gold" / "promises.csv") == []


def test_two_files_for_one_company(packet, project):
    wb = load_workbook(packet)
    ws = wb["Passages"]
    col = columns(ws)
    fill(ws, col, 2, label="Unsure")
    path = returned(project, wb)
    shutil.copy(path, path.with_name("EXMP_packet_v1 (1).xlsx"))
    result = run("import-labels", code=1)
    report = (project / "evals" / "gold" / "import_report.md").read_text(encoding="utf-8")
    assert "Keep only one returned file per company" in report
    assert len(read_csv(project / "evals" / "gold" / "passages.csv")) == 1
    assert "EXMP" in result.output


def test_import_without_files_says_where_to_put_them(project):
    result = run("import-labels", code=2)
    assert "Put the returned packets there" in " ".join(result.output.split())
