"""The whole Phase 2 loop: pipeline -> packets -> labels -> import -> eval -> report."""

import json

from openpyxl import load_workbook
from typer.testing import CliRunner

from aipb import cli
from aipb.labeling import schema as S

runner = CliRunner()


def run(*args, code=0):
    result = runner.invoke(cli.app, list(args))
    assert result.exit_code == code, result.output
    return result


def label_packet(project):
    path = project / "exports" / "packets" / "EXMP_packet_v1.xlsx"
    wb = load_workbook(path)
    ws = wb["Passages"]
    col = {c.value: c.column for c in ws[1]}
    col = {k: col[t] for k, t in S.HEADER.items()}
    for r in range(2, ws.max_row + 1):
        text = str(ws.cell(r, col["text"]).value)
        if "25 percent of total revenue" in text:
            ws.cell(r, col["label"], S.LABEL_PROMISE)
            ws.cell(r, col["p1_quote"], "We believe our AI-enabled maintenance software will "
                    "account for more than 25 percent of total revenue by 2026")  # fmt: skip
            ws.cell(r, col["p1_claim_type"], "revenue")
            ws.cell(r, col["p1_target"], "more than 25 percent")
            ws.cell(r, col["p1_deadline"], "2026")
        elif "double in 2025" in text:
            ws.cell(r, col["label"], S.LABEL_PROMISE)
            ws.cell(r, col["p1_quote"],
                    "We now expect AI-related software revenue to double in 2025")  # fmt: skip
            ws.cell(r, col["p1_claim_type"], "revenue")
            ws.cell(r, col["p1_deadline"], "2025")
        else:
            ws.cell(r, col["label"], S.LABEL_NONE)
    out = project / "evals" / "gold" / "returned"
    out.mkdir(parents=True, exist_ok=True)
    wb.save(out / path.name)


def test_eval_end_to_end(llm_project, fake_claude):
    run("filter", "-u", "test")
    run("extract", "-u", "test")
    run("packets", "-u", "test", "--total", "40", "--non-keyword-share", "0.2")
    label_packet(llm_project)
    run("import-labels")
    readme = llm_project / "README.md"
    readme.write_text(
        "# x\n\n| Date | Set | F1 |\n|---|---|---|\n<!-- eval-history:start -->\n"
        "| (Phase 2) | | |\n<!-- eval-history:end -->\n",
        encoding="utf-8",
    )
    out = run("eval", "-u", "test").output
    assert "Extraction (promise level)" in out

    results = sorted((llm_project / "evals" / "results").glob("*.json"))
    assert len(results) == 1
    data = json.loads(results[0].read_text(encoding="utf-8"))
    ex = data["extraction"]
    assert ex["tp"] == 2 and ex["fn"] == 0  # both gold promises found
    assert data["quote_fidelity"]["stored_quotes_verbatim"] == 1.0
    assert data["gold"]["random_non_keyword_passages"] >= 1
    assert data["prefilter"]["with_a_promise"] == 0
    assert data["split"] == "dev" and data["prompts"] == ["extract/v1", "filter/v1"]

    text = readme.read_text(encoding="utf-8")
    assert "(Phase 2)" not in text and "| dev (" in text
    dis = list((llm_project / "exports" / "disagreements").glob("*.xlsx"))
    assert dis  # Nick's review workbook


def test_test_split_needs_a_milestone(llm_project):
    result = run("eval", "-u", "test", "--split", "test", code=2)
    assert "milestones" in " ".join(result.output.split())


def test_eval_without_gold_says_what_is_missing(llm_project):
    result = run("eval", "-u", "test", code=2)
    assert "No gold labels" in result.output


def test_compare_builds_the_ab_table(llm_project, fake_claude):
    run("filter", "-u", "test")
    run("extract", "-u", "test")
    run("extract", "-u", "test", "--variant", "sonnet")
    run("packets", "-u", "test", "--total", "40", "--non-keyword-share", "0.2")
    label_packet(llm_project)
    run("import-labels")
    run("eval", "-u", "test")
    run("eval", "-u", "test", "--variant", "sonnet")
    out = run("compare").output
    assert "| default |" in out and "| sonnet |" in out
    assert (llm_project / "evals" / "results" / "ab_dev.md").exists()
