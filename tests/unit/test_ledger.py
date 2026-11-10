from decimal import Decimal

import pytest

from aipb.budget.ledger import CallRecord, Ledger, LedgerCorrupt


def _rec(call_id: str, cost: str) -> CallRecord:
    return CallRecord(
        call_id=call_id,
        ts="2026-11-10T00:00:00+00:00",
        run_id="r",
        stage="s",
        model="claude-haiku-5-5",
        prompt_version="v1",
        input_hash="abc",
        is_batch=True,
        batch_id="b1",
        input_tokens=10,
        output_tokens=5,
        cache_read_tokens=1,
        cache_write_5m_tokens=2,
        cache_write_1h_tokens=3,
        thinking_tokens=4,
        latency_ms=None,
        cost_usd=Decimal(cost),
        status="ok",
        device="test",
    )


def test_round_trip_keeps_exact_decimal(ledger):
    ledger.append_call(_rec("a", "0.0000123456789"))
    (back,) = Ledger(ledger.directory).calls()
    assert back == _rec("a", "0.0000123456789")
    assert ledger.total_spent() == Decimal("0.0000123456789")


def test_union_merge_duplicates_are_counted_once(ledger):
    ledger.append_call(_rec("a", "0.10"))
    ledger.append_call(_rec("b", "0.20"))
    # Simulate git's union merge re-adding a line both sides had.
    line = ledger.calls_path.read_text(encoding="utf-8").splitlines()[0]
    with ledger.calls_path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(line + "\n")
    assert Ledger(ledger.directory).total_spent() == Decimal("0.30")


def test_corrupt_line_fails_closed(ledger):
    ledger.append_call(_rec("a", "0.10"))
    with ledger.calls_path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write("<<<<<<< HEAD\n")
    with pytest.raises(LedgerCorrupt, match="line 2"):
        Ledger(ledger.directory).total_spent()


def test_lines_use_lf_endings(ledger):
    ledger.append_call(_rec("a", "0.10"))
    assert b"\r\n" not in ledger.calls_path.read_bytes()
