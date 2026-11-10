from dataclasses import replace
from decimal import Decimal

import pytest

from aipb.budget.guard import (
    BudgetConfig,
    BudgetExceeded,
    BudgetGuard,
    ConfirmationRequired,
    PromptTooLarge,
    RunBudgetExceeded,
)
from aipb.budget.ledger import CallRecord, Ledger


def _spend(ledger: Ledger, amount: str, run_id: str = "seed", call_id: str = "c0") -> None:
    ledger.append_call(
        CallRecord(
            call_id=call_id,
            ts="2026-11-10T00:00:00+00:00",
            run_id=run_id,
            stage="seed",
            model="claude-haiku-5-5",
            prompt_version="v0",
            input_hash="h",
            is_batch=False,
            batch_id=None,
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=0,
            cache_write_5m_tokens=0,
            cache_write_1h_tokens=0,
            thinking_tokens=0,
            latency_ms=1,
            cost_usd=Decimal(amount),
            status="ok",
            device="test",
        )
    )


def test_fresh_budget(guard):
    st = guard.status()
    assert st.spent == 0
    assert st.cap == Decimal("15.00")
    assert st.reserve_locked == Decimal("4.00")
    assert st.total_credit == Decimal("19.00")
    assert st.remaining == Decimal("15.00")


def test_confirm_threshold(guard):
    guard.preflight(Decimal("0.50"), confirm=False)  # at the threshold: fine
    with pytest.raises(ConfirmationRequired):
        guard.preflight(Decimal("0.51"), confirm=False)
    guard.preflight(Decimal("0.51"), confirm=True)


def test_hard_cap_cannot_be_confirmed_away(guard, ledger):
    _spend(ledger, "14.80")
    with pytest.raises(BudgetExceeded):
        guard.preflight(Decimal("0.30"), confirm=True)
    guard.preflight(Decimal("0.20"), confirm=False)


def test_reserve_unlock_raises_cap(paths, ledger, pricing):
    cfg = replace(BudgetConfig.load(paths.budget_config), reserve_unlocked_usd=Decimal("1.00"))
    g = BudgetGuard(cfg, ledger, pricing)
    assert g.status().cap == Decimal("16.00")
    assert g.status().reserve_locked == Decimal("3.00")


@pytest.mark.parametrize(
    "field,value",
    [("reserve_unlocked_usd", Decimal("4.01")), ("app_cap_usd", Decimal("15.01"))],
)
def test_config_rejects_impossible_budgets(paths, field, value):
    base = BudgetConfig.load(paths.budget_config)
    with pytest.raises(ValueError):
        replace(base, **{field: value})


def test_reservation_lifecycle(guard, ledger):
    run = guard.start_run(command="t", stage="t", estimate=Decimal("2.00"), confirm=True)
    assert guard.status().reserved == Decimal("2.00")
    assert guard.status().remaining == Decimal("13.00")

    _spend(ledger, "0.50", run_id=run.run_id, call_id="c1")
    st = guard.status()
    assert (st.spent, st.reserved, st.remaining) == (
        Decimal("0.50"),
        Decimal("1.50"),
        Decimal("13.00"),
    )

    run.finish()
    st = guard.status()
    assert (st.reserved, st.remaining) == (Decimal("0"), Decimal("14.50"))


def test_crashed_run_keeps_its_reservation_until_released(guard, paths, pricing):
    run = guard.start_run(command="t", stage="t", estimate=Decimal("1.00"), confirm=True)
    fresh = BudgetGuard(BudgetConfig.load(paths.budget_config), Ledger(paths.ledger_dir), pricing)
    assert fresh.status().reserved == Decimal("1.00")
    fresh.release_run(run.run_id)
    assert fresh.status().reserved == 0


def test_reservations_count_against_new_runs(guard):
    guard.start_run(command="a", stage="a", estimate=Decimal("14.00"), confirm=True)
    with pytest.raises(BudgetExceeded):
        guard.start_run(command="b", stage="b", estimate=Decimal("1.01"), confirm=True)


def test_call_must_fit_inside_its_run(guard):
    with guard.start_run(command="t", stage="t", estimate=Decimal("0.01"), confirm=False) as run:
        run.authorize_call(Decimal("0.01"))
        with pytest.raises(RunBudgetExceeded):
            run.authorize_call(Decimal("0.0101"))


def test_context_manager_records_error_status(guard, ledger):
    with (
        pytest.raises(RuntimeError),
        guard.start_run(command="t", stage="t", estimate=Decimal("0.01"), confirm=False),
    ):
        raise RuntimeError("boom")
    (state,) = ledger.runs().values()
    assert state.finish is not None and state.finish.status == "error"


def test_prompt_size_limit(guard):
    guard.check_prompt_size(100_000)
    with pytest.raises(PromptTooLarge):
        guard.check_prompt_size(100_001)
