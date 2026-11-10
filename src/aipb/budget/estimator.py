"""Cheap, conservative cost estimates made before any request is sent.

The estimate deliberately runs high:
- input tokens come from a low chars-per-token ratio plus a safety margin;
- output is assumed to use all of max_tokens (thinking tokens count toward max_tokens);
- if the request marks anything for caching, all input is priced at the cache-write rate.

Phase 2 calibrates chars_per_token against the free count_tokens endpoint.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import yaml

from aipb.budget.pricing import PricingTable, TokenUsage

_PROMPT_KEYS = ("system", "messages", "tools", "output_config", "tool_choice")


@dataclass(frozen=True)
class Estimator:
    chars_per_token: float = 3.0
    safety_margin: float = 1.15
    per_request_overhead_tokens: int = 50

    @classmethod
    def load(cls, path: Path) -> Estimator:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        est = raw.get("estimator", {})
        return cls(
            chars_per_token=float(est.get("chars_per_token", 3.0)),
            safety_margin=float(est.get("safety_margin", 1.15)),
            per_request_overhead_tokens=int(est.get("per_request_overhead_tokens", 50)),
        )

    def tokens_for_text(self, text: str) -> int:
        return math.ceil(len(text) / self.chars_per_token * self.safety_margin)

    def input_tokens(self, params: dict) -> int:
        prompt_part = {k: params[k] for k in _PROMPT_KEYS if k in params}
        text = json.dumps(prompt_part, ensure_ascii=False, sort_keys=True, default=str)
        return self.tokens_for_text(text) + self.per_request_overhead_tokens

    def worst_case_cost(self, pricing: PricingTable, params: dict, *, batch: bool) -> Decimal:
        model = params["model"]
        tokens_in = self.input_tokens(params)
        tokens_out = int(params["max_tokens"])
        serialized = json.dumps(params, default=str)
        if "cache_control" in serialized:
            one_hour = '"ttl": "1h"' in serialized
            usage = TokenUsage(
                cache_write_1h_tokens=tokens_in if one_hour else 0,
                cache_write_5m_tokens=0 if one_hour else tokens_in,
                output_tokens=tokens_out,
            )
        else:
            usage = TokenUsage(input_tokens=tokens_in, output_tokens=tokens_out)
        return pricing.cost(model, usage, batch=batch)
