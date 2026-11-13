"""Evidence picking: per-filing cap, no repeats, and deadline-period slots first (D52)."""

from aipb.verify.context import pick_evidence


def row(pid, acc, date, sha=None, score=-1.0):
    return {
        "passage_id": pid,
        "accession": acc,
        "filing_date": date,
        "form": "8-K",
        "section": "ex99",
        "text": f"text {pid}",
        "text_sha256": sha or pid,
        "score": score,
    }


def test_caps_per_filing_and_skips_repeated_text():
    rows = [row("a1", "A", "2025-03-01"), row("a2", "A", "2025-03-01"),
            row("a3", "A", "2025-03-01"), row("b1", "B", "2025-06-01", sha="a1")]  # fmt: skip
    got = pick_evidence(rows, k=8)
    assert [e.passage_id for e in got] == ["a1", "a2"]
    assert [e.eid for e in got] == ["E1", "E2"]


def test_deadline_period_rows_get_reserved_slots():
    later = [row(f"l{i}", f"L{i}", f"2026-0{i}-01") for i in range(1, 9)]
    window = [row("w1", "W", "2025-02-26"), row("w2", "W", "2025-02-26"),
              row("w3", "W2", "2025-02-26"), row("w4", "W3", "2025-03-01")]  # fmt: skip
    got = pick_evidence(later, k=8, reserved=window, reserved_k=3)
    ids = [e.passage_id for e in got]
    assert len(ids) == 8
    assert {"w1", "w2", "w3"} <= set(ids) and "w4" not in ids  # only 3 reserved slots
    assert ids == sorted(ids, key=lambda p: next(e.filing_date for e in got if e.passage_id == p))
    # Without a deadline window, ranking alone decides.
    assert all(e.passage_id.startswith("l") for e in pick_evidence(later, k=8))


def test_reserved_rows_respect_the_per_filing_cap_across_both_lists():
    window = [row("w1", "W", "2025-02-26"), row("w2", "W", "2025-02-26")]
    later = [row("w3", "W", "2025-02-26"), row("l1", "L", "2026-01-01")]
    got = [e.passage_id for e in pick_evidence(later, k=8, reserved=window)]
    assert got == ["w1", "w2", "l1"]
