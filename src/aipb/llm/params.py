"""Shared request building: prompt files, per-stage settings, structured-output parsing.

Prompts live in prompts/<stage>/<version>.md and are versioned by file name. Every result
records "<stage>/<version>" and the model. The request body (system prompt, schema,
settings) is part of the cache key, so editing a prompt file can never serve an old
answer, even if someone forgets to bump the version.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from aipb.llm.client import LLMResult


def thinking_params(stage_cfg: dict) -> dict:
    """Translate a stage's thinking/effort settings into request parameters.

    Haiku 5.5 thinks by default (effort medium) and thinking bills as output, so every
    stage states its choice. "disabled" is valid on Haiku 5.5 at effort high or below;
    Sonnet 5.5 rejects "disabled" and uses "between_tools" instead.
    """
    params: dict = {}
    thinking = stage_cfg.get("thinking")
    if thinking in ("disabled", "adaptive", "between_tools"):
        params["thinking"] = {"type": thinking}
    elif thinking is not None:
        raise ValueError(f"Unknown thinking setting {thinking!r}")
    if stage_cfg.get("effort"):
        params["output_config"] = {"effort": stage_cfg["effort"]}
    return params


@dataclass(frozen=True)
class Prompt:
    stage: str
    version: str
    text: str

    @property
    def id(self) -> str:
        return f"{self.stage}/{self.version}"


def load_prompt(prompts_dir: Path, stage: str, version: str) -> Prompt:
    path = prompts_dir / stage / f"{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"No prompt file {path}")
    return Prompt(stage, version, path.read_text(encoding="utf-8").strip())


def stage_settings(stages: dict, stage: str, variant: str | None = None) -> dict:
    """The stage's settings, with a named variant's overrides applied (for A/B tests)."""
    if stage not in stages:
        raise KeyError(f"No settings for stage {stage!r} in config/stages.yaml")
    cfg = dict(stages[stage])
    variants = cfg.pop("variants", {}) or {}
    if variant and variant != "default":
        if variant not in variants:
            raise KeyError(f"Stage {stage!r} has no variant {variant!r} in config/stages.yaml")
        cfg.update(variants[variant])
    return cfg


def build_params(
    cfg: dict, prompt: Prompt, user_content: str | list, schema: dict | None = None
) -> dict:
    """A Messages API request: cached system prompt, one user turn, optional JSON schema."""
    params: dict = {
        "model": cfg["model"],
        "max_tokens": int(cfg["max_tokens"]),
        "system": [{"type": "text", "text": prompt.text, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user_content}],
        **thinking_params(cfg),
    }
    if schema is not None:
        params.setdefault("output_config", {})["format"] = {
            "type": "json_schema",
            "schema": schema,
        }
    return params


class OutputError(ValueError):
    """The model's output can't be used (refusal, truncation, invalid JSON)."""


def parse_json(result: LLMResult) -> dict:
    """The JSON object from a structured-output response, or OutputError explaining why not."""
    if result.status != "ok":
        raise OutputError(f"request status {result.status}")
    stop = result.stop_reason
    if stop == "refusal":
        raise OutputError("the model declined (stop_reason=refusal)")
    if stop == "max_tokens":
        raise OutputError("output was cut off (stop_reason=max_tokens); raise max_tokens")
    text = result.text()
    if not text:
        raise OutputError("no text block in the response")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OutputError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise OutputError("expected a JSON object")
    return data


def nullable(schema: dict) -> dict:
    return {"anyOf": [schema, {"type": "null"}]}


def obj(properties: dict) -> dict:
    """A strict object schema: every property required, no extras (structured outputs)."""
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }
