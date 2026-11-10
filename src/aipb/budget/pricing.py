"""Exact per-call cost from token usage, using config/pricing.yaml.

All money is Decimal. Floats never touch a dollar amount.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import yaml

MTOK = Decimal(1_000_000)


class UnknownModelError(KeyError):
    pass


def _dec(value: object) -> Decimal:
    return Decimal(str(value))


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_5m_tokens: int = 0
    cache_write_1h_tokens: int = 0

    @property
    def cache_write_tokens(self) -> int:
        return self.cache_write_5m_tokens + self.cache_write_1h_tokens

    @property
    def prompt_tokens(self) -> int:
        """Prompt length as the pricing page defines it: every input token, cached or not."""
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens


@dataclass(frozen=True)
class PriceTier:
    max_prompt_tokens: int | None  # inclusive upper bound; None = no upper bound
    input: Decimal
    cache_write_5m: Decimal
    cache_write_1h: Decimal
    cache_read: Decimal
    output: Decimal


@dataclass(frozen=True)
class ModelPricing:
    model: str
    tiers: tuple[PriceTier, ...]

    def tier_for(self, prompt_tokens: int) -> PriceTier:
        for tier in self.tiers:
            if tier.max_prompt_tokens is None or prompt_tokens <= tier.max_prompt_tokens:
                return tier
        return self.tiers[-1]


@dataclass(frozen=True)
class PricingTable:
    models: dict[str, ModelPricing]
    batch_multiplier: Decimal
    verified_on: str
    source: str

    @classmethod
    def load(cls, path: Path) -> PricingTable:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        models: dict[str, ModelPricing] = {}
        for name, spec in raw["models"].items():
            tiers = tuple(
                PriceTier(
                    max_prompt_tokens=t["max_prompt_tokens"],
                    input=_dec(t["input"]),
                    cache_write_5m=_dec(t["cache_write_5m"]),
                    cache_write_1h=_dec(t["cache_write_1h"]),
                    cache_read=_dec(t["cache_read"]),
                    output=_dec(t["output"]),
                )
                for t in spec["tiers"]
            )
            if not tiers or tiers[-1].max_prompt_tokens is not None:
                raise ValueError(f"{name}: the last pricing tier must have max_prompt_tokens: null")
            models[name] = ModelPricing(model=name, tiers=tiers)
        return cls(
            models=models,
            batch_multiplier=_dec(raw["batch_multiplier"]),
            verified_on=str(raw["verified_on"]),
            source=str(raw["source"]),
        )

    def model(self, name: str) -> ModelPricing:
        try:
            return self.models[name]
        except KeyError:
            raise UnknownModelError(
                f"No pricing for model {name!r}. Add it to config/pricing.yaml first."
            ) from None

    def cost(self, model: str, usage: TokenUsage, *, batch: bool) -> Decimal:
        tier = self.model(model).tier_for(usage.prompt_tokens)
        total = (
            usage.input_tokens * tier.input
            + usage.cache_read_tokens * tier.cache_read
            + usage.cache_write_5m_tokens * tier.cache_write_5m
            + usage.cache_write_1h_tokens * tier.cache_write_1h
            + usage.output_tokens * tier.output
        ) / MTOK
        if batch:
            total *= self.batch_multiplier
        return total
