"""Cost math checked by hand against config/pricing.yaml (verified 2026-11-10)."""

from decimal import Decimal

import pytest

from aipb.budget.pricing import TokenUsage, UnknownModelError

HAIKU = "claude-haiku-5-5"
SONNET = "claude-sonnet-5-5"
M = 1_000_000


def test_pricing_file_is_dated(pricing):
    from datetime import date

    assert date.fromisoformat(pricing.verified_on) >= date(2026, 11, 10)  # re-checked dates move
    assert pricing.source.startswith("https://platform.claude.com/")


def test_haiku_interactive_one_million_in_and_out(pricing):
    # 1M input at $0.10 + 1M output at $0.50; a 2M-token prompt would hit the high tier,
    # so split it into a realistic request size instead.
    usage = TokenUsage(input_tokens=50_000, output_tokens=10_000)
    expected = Decimal("50000") * Decimal("0.10") / M + Decimal("10000") * Decimal("0.50") / M
    assert pricing.cost(HAIKU, usage, batch=False) == expected == Decimal("0.01")


def test_batch_halves_everything(pricing):
    usage = TokenUsage(input_tokens=50_000, output_tokens=10_000)
    assert pricing.cost(HAIKU, usage, batch=True) == Decimal("0.005")


def test_haiku_cache_prices(pricing):
    assert pricing.cost(HAIKU, TokenUsage(cache_read_tokens=M // 10), batch=False) == Decimal(
        "0.001"
    )  # $0.01 / MTok
    assert pricing.cost(HAIKU, TokenUsage(cache_write_5m_tokens=80_000), batch=False) == Decimal(
        "0.01"
    )  # $0.125 / MTok
    assert pricing.cost(HAIKU, TokenUsage(cache_write_1h_tokens=50_000), batch=False) == Decimal(
        "0.01"
    )  # $0.20 / MTok


def test_tier_boundary_is_inclusive_at_100k(pricing):
    at_limit = TokenUsage(input_tokens=100_000)
    over = TokenUsage(input_tokens=100_001)
    assert pricing.cost(HAIKU, at_limit, batch=False) == Decimal("0.01")  # $0.10 / MTok
    assert pricing.cost(HAIKU, over, batch=False) == Decimal("0.0500005")  # $0.50 / MTok


def test_cached_tokens_count_toward_the_tier(pricing):
    # 50k fresh + 60k cache reads = 110k prompt -> the over-100k prices apply to both.
    usage = TokenUsage(input_tokens=50_000, cache_read_tokens=60_000)
    expected = Decimal("50000") * Decimal("0.50") / M + Decimal("60000") * Decimal("0.05") / M
    assert pricing.cost(HAIKU, usage, batch=False) == expected == Decimal("0.028")


def test_sonnet_prices(pricing):
    usage = TokenUsage(input_tokens=10_000, output_tokens=1_000, cache_read_tokens=10_000)
    # 10k * $2 + 1k * $10 + 10k * $0.10, per million
    assert pricing.cost(SONNET, usage, batch=False) == Decimal("0.031")
    assert pricing.cost(SONNET, usage, batch=True) == Decimal("0.0155")


def test_unknown_model_is_refused(pricing):
    with pytest.raises(UnknownModelError):
        pricing.cost("claude-opus-5-5", TokenUsage(input_tokens=1), batch=False)
