"""D58: a pending item's public page says why it's pending in plain language, never with
the gate's internal reason (draft statuses, field names, confidence scores)."""

import pytest

from aipb.verify import gate
from aipb.verify.targets import GROWTH_HOLD
from aipb.verify.tier1 import PENDING_REASONS

# Words that would hint at an unpublished verdict or expose internals.
INTERNAL = ("walk", "deliver", "on track", "on_track", "no evidence", "_", "draft", "confidence",
            "rubric", "tier", "key finding", "verdict", "broke")  # fmt: skip


def every_gate_reason() -> list[str]:
    """Each reason the gate and the verify runner can give, in the form they give it."""
    return [
        "open error report",
        "not verified yet",
        *[f"rubric: {r.replace('_', ' ')}" for r in PENDING_REASONS if r != "none"],
        "walked back needs two confident checks",
        "checks disagree (walked_back/explicit vs delivered/none)",
        "checks disagree (delivered vs no_evidence_yet)",
        "confidence 0.70 below 0.75",
        "explanation missing or its citations did not check out",
        "explanation was written for a different status",
        GROWTH_HOLD,
    ]


@pytest.mark.parametrize("reason", every_gate_reason())
def test_every_gate_reason_has_its_own_plain_sentence(reason):
    text = gate.public_reason(reason)
    assert text != gate.PUBLIC_REASON_OTHER, reason
    assert text.endswith(".") and text[0].isupper()
    assert not any(w in text.lower() for w in INTERNAL), text
    assert not any(ch.isdigit() for ch in text), text


def test_invalid_verdict_problems_get_the_general_sentence():
    # Joined verdict problems name statuses and fields; none of that reaches the page.
    for problem in (
        "non-neutral wording in key_finding: ['broke']",
        "vague_deliverable applies only to specificity-1 promises",
        "walked_back without saying explicit or silent; on_track after the deadline has passed",
        "cites evidence that was not provided: ['E9']",
    ):
        assert gate.public_reason(problem) == gate.PUBLIC_REASON_OTHER
    assert not any(w in gate.PUBLIC_REASON_OTHER.lower() for w in INTERNAL)


def test_a_missing_reason_reads_as_not_checked_yet():
    assert (
        gate.public_reason(None) == gate.public_reason("") == gate.public_reason("not verified yet")
    )
