from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from aipb.budget.estimator import Estimator
from aipb.budget.guard import BudgetConfig, BudgetGuard
from aipb.budget.ledger import Ledger
from aipb.budget.pricing import PricingTable
from aipb.llm.cache import OutputCache
from aipb.paths import Paths

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _no_real_keys(monkeypatch):
    """Tests must never see a real key or reach the network."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("AIPAYBACK_API_KEY", raising=False)
    monkeypatch.delenv("AIPAYBACK_OFFLINE", raising=False)


@pytest.fixture
def root(tmp_path, monkeypatch) -> Path:
    """A throwaway project root with the real config files and an empty data folder."""
    shutil.copytree(REPO / "config", tmp_path / "config")
    (tmp_path / "data" / "ledger").mkdir(parents=True)
    (tmp_path / "data" / "outputs").mkdir(parents=True)
    monkeypatch.setenv("AIPAYBACK_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture
def paths(root) -> Paths:
    return Paths(root)


@pytest.fixture
def pricing(paths) -> PricingTable:
    return PricingTable.load(paths.pricing_config)


@pytest.fixture
def ledger(paths) -> Ledger:
    return Ledger(paths.ledger_dir)


@pytest.fixture
def guard(paths, ledger, pricing) -> BudgetGuard:
    return BudgetGuard(BudgetConfig.load(paths.budget_config), ledger, pricing, device="test")


@pytest.fixture
def cache(paths) -> OutputCache:
    return OutputCache(paths.outputs_dir)


@pytest.fixture
def estimator() -> Estimator:
    return Estimator()


class FakeMessage:
    def __init__(self, *, text="OK", stop_reason="end_turn", usage=None, model="claude-haiku-5-5"):
        self.stop_reason = stop_reason
        self.usage = usage or SimpleNamespace(
            input_tokens=1000,
            output_tokens=200,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
            cache_creation=None,
            output_tokens_details=None,
        )
        self._text = text
        self._model = model

    def model_dump(self, mode="json"):
        return {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": self._model,
            "content": [{"type": "text", "text": self._text}],
            "stop_reason": self.stop_reason,
            "usage": {
                "input_tokens": self.usage.input_tokens,
                "output_tokens": self.usage.output_tokens,
            },
        }


class FakeSdk:
    """Stands in for anthropic.Anthropic. Records every call; never touches the network."""

    def __init__(self, api_key: str, *, message: FakeMessage | None = None, error=None):
        self.api_key = api_key
        self.calls: list[dict] = []
        self._message = message or FakeMessage()
        self._error = error
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **params):
        self.calls.append(params)
        if self._error:
            raise self._error
        return self._message


@pytest.fixture
def fake_sdk_factory():
    created: list[FakeSdk] = []

    def factory(api_key: str, **kwargs) -> FakeSdk:
        sdk = FakeSdk(api_key, **kwargs)
        created.append(sdk)
        return sdk

    factory.created = created  # type: ignore[attr-defined]
    return factory
