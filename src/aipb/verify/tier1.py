"""Tier 1: one Haiku judge call per promise (structured output), validated by code."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from aipb.llm.client import LLMResult
from aipb.llm.params import OutputError, Prompt, build_params, obj, parse_json
from aipb.verify.context import VerifyContext, render
from aipb.verify.neutral import banned_words

STAGE = "verify_t1"
STATUSES = ("delivered", "on_track", "no_evidence_yet", "walked_back")
DISPLAY = {
    "delivered": "Delivered",
    "on_track": "On track",
    "no_evidence_yet": "No evidence yet",
    "walked_back": "Walked back",
}

# Rubric conditions (Nick's final rubric and evidence map, D41) under which a promise is
# published as "Status pending review" whatever the evidence shows. They are judgments, so
# the model names one; the gate then holds the item and no second check is paid for.
PENDING_REASONS = (
    "none",
    "vague_deliverable",  # specificity 1 without a named product, feature or program
    "run_rate_or_realized_unclear",  # the promise doesn't say which, and context doesn't either
    "basis_changed",  # company switched GAAP/non-GAAP, currency basis or metric definition
    "undefined_base",  # a percentage target without saying of what, or from which year
)

VERDICT_SCHEMA = obj(
    {
        "status": {"type": "string", "enum": list(STATUSES)},
        "walked_back_kind": {"type": "string", "enum": ["explicit", "silent", "none"]},
        "confidence": {"type": "number"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
        "number_ids": {"type": "array", "items": {"type": "string"}},
        "key_finding": {"type": "string"},
        "pending_reason": {"type": "string", "enum": list(PENDING_REASONS)},
    }
)


@dataclass
class Verdict:
    tier: str  # "1" or "2"
    status: str
    walked_back_kind: str
    confidence: float
    evidence_ids: list[str]
    number_ids: list[str]
    key_finding: str
    valid: bool = True
    problems: list[str] = field(default_factory=list)
    pending_reason: str = "none"

    def to_dict(self) -> dict:
        return asdict(self)


def build_request_params(ctx: VerifyContext, cfg: dict, prompt: Prompt) -> dict:
    return build_params(cfg, prompt, render(ctx), VERDICT_SCHEMA)


def validate(
    raw: dict,
    ctx: VerifyContext,
    tier: str,
    extra_evidence: set[str] = frozenset(),
    extra_numbers: set[str] = frozenset(),
) -> Verdict:
    """Turn the model's JSON into a Verdict, checking it against what code knows."""
    v = Verdict(
        tier=tier,
        status=raw.get("status", ""),
        walked_back_kind=raw.get("walked_back_kind", "none"),
        confidence=max(0.0, min(1.0, float(raw.get("confidence") or 0.0))),
        evidence_ids=list(dict.fromkeys(raw.get("evidence_ids") or [])),
        number_ids=list(dict.fromkeys(raw.get("number_ids") or [])),
        key_finding=(raw.get("key_finding") or "").strip(),
        pending_reason=raw.get("pending_reason") or "none",
    )
    if v.status not in STATUSES:
        v.problems.append(f"unknown status {v.status!r}")
    if v.pending_reason not in PENDING_REASONS:
        v.problems.append(f"unknown pending_reason {v.pending_reason!r}")
    if v.pending_reason == "vague_deliverable" and ctx.promise.get("specificity") not in (1, None):
        v.problems.append("vague_deliverable applies only to specificity-1 promises")
    known_e = ctx.evidence_ids() | set(extra_evidence)
    known_n = ctx.number_ids() | set(extra_numbers)
    if bad := [e for e in v.evidence_ids if e not in known_e]:
        v.problems.append(f"cites evidence that was not provided: {bad}")
    if bad := [n for n in v.number_ids if n not in known_n]:
        v.problems.append(f"cites numbers that were not provided: {bad}")
    if v.status == "on_track" and ctx.deadline_passed:
        v.problems.append("on_track after the deadline has passed")
    if v.status == "walked_back":
        if v.walked_back_kind == "none":
            v.problems.append("walked_back without saying explicit or silent")
        if v.walked_back_kind == "explicit" and not v.evidence_ids:
            v.problems.append("explicit walk-back must cite the passage that lowers or drops it")
        if v.walked_back_kind == "silent" and not ctx.silent_walkback_possible:
            # The rubric's conditions for silence are facts code checks, not judgments.
            v.problems.append("silent walk-back conditions not met; downgraded to no_evidence_yet")
            v.status, v.walked_back_kind = "no_evidence_yet", "none"
    elif v.walked_back_kind != "none":
        v.walked_back_kind = "none"
    # Checked after any downgrade. A silent walk-back is about absence, so it has nothing
    # to cite; everything else that claims an outcome must point at its evidence.
    silent = v.status == "walked_back" and v.walked_back_kind == "silent"
    if (
        v.status in ("delivered", "on_track", "walked_back")
        and not silent
        and not (v.evidence_ids or v.number_ids)
    ):
        v.problems.append(f"status {v.status} cites no evidence or numbers")
    if words := banned_words(v.key_finding):
        v.problems.append(f"non-neutral wording in key_finding: {words}")
    v.valid = not [p for p in v.problems if "downgraded" not in p]
    return v


def parse(result: LLMResult, ctx: VerifyContext) -> Verdict:
    try:
        raw = parse_json(result)
    except OutputError as exc:
        return Verdict("1", "", "none", 0.0, [], [], "", valid=False, problems=[str(exc)])
    return validate(raw, ctx, "1")


def dumps(v: Verdict) -> str:
    return json.dumps(v.to_dict(), sort_keys=True)
