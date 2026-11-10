from decimal import Decimal
from types import SimpleNamespace

import pytest

from aipb.budget.guard import RunBudgetExceeded
from aipb.llm import client as client_mod
from aipb.llm.client import LLMClient, MissingApiKey, OfflineCacheMiss
from tests.conftest import FakeMessage

PARAMS = {
    "model": "claude-haiku-5-5",
    "max_tokens": 300,
    "thinking": {"type": "disabled"},
    "messages": [{"role": "user", "content": "Is this a forward-looking AI claim?"}],
}


FAKE_APP_KEY = "app-key"  # pragma: allowlist secret


def make_client(guard, cache, estimator, factory, *, api_key=FAKE_APP_KEY, offline=False):
    return LLMClient(
        guard=guard,
        cache=cache,
        estimator=estimator,
        api_key=api_key,
        offline=offline,
        device="test",
        sdk_factory=factory,
    )


def test_first_call_is_billed_logged_and_cached(guard, cache, estimator, fake_sdk_factory):
    llm = make_client(guard, cache, estimator, fake_sdk_factory)
    with guard.start_run(
        command="t", stage="filter", estimate=Decimal("0.01"), confirm=False
    ) as run:
        result = llm.create(run=run, stage="filter", prompt_version="v1", params=PARAMS)

    assert result.text() == "OK" and not result.cached
    # 1000 in * $0.10 + 200 out * $0.50, per million
    assert result.cost_usd == Decimal("0.0002")
    (rec,) = guard.ledger.calls()
    assert (rec.stage, rec.prompt_version, rec.cost_usd, rec.status) == (
        "filter",
        "v1",
        Decimal("0.0002"),
        "ok",
    )
    assert cache.count("filter") == 1


def test_second_identical_call_is_free(guard, cache, estimator, fake_sdk_factory):
    llm = make_client(guard, cache, estimator, fake_sdk_factory)
    with guard.start_run(command="t", stage="s", estimate=Decimal("0.01"), confirm=False) as run:
        llm.create(run=run, stage="s", prompt_version="v1", params=PARAMS)
        again = llm.create(run=run, stage="s", prompt_version="v1", params=dict(PARAMS))
    assert again.cached and again.cost_usd == 0
    assert len(fake_sdk_factory.created[0].calls) == 1
    assert len(guard.ledger.calls()) == 1


def test_new_prompt_version_is_a_cache_miss(guard, cache, estimator, fake_sdk_factory):
    llm = make_client(guard, cache, estimator, fake_sdk_factory)
    with guard.start_run(command="t", stage="s", estimate=Decimal("0.01"), confirm=False) as run:
        llm.create(run=run, stage="s", prompt_version="v1", params=PARAMS)
        llm.create(run=run, stage="s", prompt_version="v2", params=PARAMS)
    assert len(fake_sdk_factory.created[0].calls) == 2


def test_offline_mode_never_builds_a_client(guard, cache, estimator, fake_sdk_factory):
    llm = make_client(guard, cache, estimator, fake_sdk_factory, offline=True)
    with (
        pytest.raises(OfflineCacheMiss),
        guard.start_run(command="t", stage="s", estimate=Decimal("0.01"), confirm=False) as run,
    ):
        llm.create(run=run, stage="s", prompt_version="v1", params=PARAMS)
    assert fake_sdk_factory.created == []
    assert guard.ledger.calls() == []


def test_missing_app_key_refuses_instead_of_falling_back(
    guard, cache, estimator, fake_sdk_factory, monkeypatch
):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-never-be-used")
    llm = make_client(guard, cache, estimator, fake_sdk_factory, api_key=None)
    with (
        pytest.raises(MissingApiKey),
        guard.start_run(command="t", stage="s", estimate=Decimal("0.01"), confirm=False) as run,
    ):
        llm.create(run=run, stage="s", prompt_version="v1", params=PARAMS)
    assert fake_sdk_factory.created == []


def test_default_factory_passes_the_app_key_explicitly(monkeypatch):
    captured = {}

    class Capture:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-never-be-used")
    monkeypatch.setattr("anthropic.Anthropic", Capture)
    client_mod.default_sdk_factory(FAKE_APP_KEY)
    assert captured["api_key"] == FAKE_APP_KEY


def test_guard_blocks_the_call_before_it_is_sent(guard, cache, estimator, fake_sdk_factory):
    llm = make_client(guard, cache, estimator, fake_sdk_factory)
    with (
        pytest.raises(RunBudgetExceeded),
        guard.start_run(command="t", stage="s", estimate=Decimal("0.00001"), confirm=False) as run,
    ):
        llm.create(run=run, stage="s", prompt_version="v1", params=PARAMS)
    assert fake_sdk_factory.created == [] or fake_sdk_factory.created[0].calls == []


def test_refusals_are_billed_but_not_cached(guard, cache, estimator):
    def factory(key):
        from tests.conftest import FakeSdk

        return FakeSdk(key, message=FakeMessage(text="", stop_reason="refusal"))

    llm = make_client(guard, cache, estimator, factory)
    with guard.start_run(command="t", stage="s", estimate=Decimal("0.01"), confirm=False) as run:
        result = llm.create(run=run, stage="s", prompt_version="v1", params=PARAMS)
    assert result.stop_reason == "refusal"
    assert guard.ledger.calls()[0].status == "refusal"
    assert cache.count("s") == 0


def test_api_errors_are_logged_at_zero_cost(guard, cache, estimator):
    def factory(key):
        from tests.conftest import FakeSdk

        return FakeSdk(key, error=ConnectionError("network down"))

    llm = make_client(guard, cache, estimator, factory)
    with (
        pytest.raises(ConnectionError),
        guard.start_run(command="t", stage="s", estimate=Decimal("0.01"), confirm=False) as run,
    ):
        llm.create(run=run, stage="s", prompt_version="v1", params=PARAMS)
    (rec,) = guard.ledger.calls()
    assert (rec.status, rec.cost_usd) == ("error", Decimal(0))


def test_cache_write_breakdown_is_priced_per_ttl(guard, cache, estimator):
    usage = SimpleNamespace(
        input_tokens=100,
        output_tokens=10,
        cache_read_input_tokens=2000,
        cache_creation_input_tokens=3000,
        cache_creation=SimpleNamespace(
            ephemeral_5m_input_tokens=1000, ephemeral_1h_input_tokens=2000
        ),
        output_tokens_details=SimpleNamespace(thinking_tokens=0),
    )

    def factory(key):
        from tests.conftest import FakeSdk

        return FakeSdk(key, message=FakeMessage(usage=usage))

    llm = make_client(guard, cache, estimator, factory)
    with guard.start_run(command="t", stage="s", estimate=Decimal("0.01"), confirm=False) as run:
        result = llm.create(run=run, stage="s", prompt_version="v1", params=PARAMS)
    # 100*$0.10 + 2000*$0.01 + 1000*$0.125 + 2000*$0.20 + 10*$0.50, per million
    assert result.cost_usd == Decimal("0.00056")
