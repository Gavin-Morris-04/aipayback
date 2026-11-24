"""The inclusion gate: what may be published as a status, and what stays "pending review".

Rules (brief section 9.1 and the rubric), all checked by code:
- quotes verified verbatim (true by construction: unverified quotes are never stored);
- a valid verdict with confidence >= threshold;
- a cited explanation whose citations all check out and whose wording is neutral;
- no open error report against the promise;
- "Walked back" needs two independent checks (Tier 1 and Tier 2) that agree;
- no check names a rubric pending condition (vague specificity-1 deliverable, unclear
  run-rate vs realized, changed basis or definition, undefined percentage base).
- the status agrees with what code computes from the reported figures (D57: a total-revenue
  growth target against the deadline year's growth; applied by the verify runner).
Anything else is published as "Status pending review" with the verified quote only.
"""

from __future__ import annotations

from dataclasses import dataclass

from aipb.verify.tier1 import DISPLAY, Verdict

PENDING = "Status pending review"
DEFAULT_THRESHOLD = 0.75


@dataclass(frozen=True)
class Decision:
    status: str  # internal status code, or "" when pending
    label: str  # what the site shows
    publishable: bool
    silent: bool
    reason: str
    source_tier: str  # "1", "2", "1+2" or ""


def held(reason: str) -> Decision:
    """Pending, for a reason found after the verdicts (a code check, a stale explanation)."""
    return Decision("", PENDING, False, False, reason, "")


def _ok(v: Verdict | None, threshold: float) -> bool:
    return v is not None and v.valid and v.confidence >= threshold


def decide(
    t1: Verdict | None,
    t2: Verdict | None,
    *,
    explanation_ok: bool,
    open_error_report: bool,
    threshold: float = DEFAULT_THRESHOLD,
) -> Decision:
    def pending(reason: str) -> Decision:
        return Decision("", PENDING, False, False, reason, "")

    if open_error_report:
        return pending("open error report")
    if t1 is None and t2 is None:
        return pending("not verified yet")
    for v in (t1, t2):
        if v is not None and v.valid and v.pending_reason != "none":
            # The rubric says these cases are published as pending, whatever the status.
            return pending(f"rubric: {v.pending_reason.replace('_', ' ')}")

    chosen: Verdict | None
    tier = ""
    if (t1 is not None and t1.status == "walked_back") or (
        t2 is not None and t2.status == "walked_back"
    ):
        # Negative statuses need two independent checks that agree.
        if not (_ok(t1, threshold) and _ok(t2, threshold)):
            return pending("walked back needs two confident checks")
        if t1.status != t2.status or t1.walked_back_kind != t2.walked_back_kind:
            return pending(
                f"checks disagree ({t1.status}/{t1.walked_back_kind} vs "
                f"{t2.status}/{t2.walked_back_kind})"
            )
        chosen, tier = t1, "1+2"
    elif _ok(t1, threshold) and _ok(t2, threshold) and t1.status != t2.status:
        # Two confident checks that disagree: never pick one.
        return pending(f"checks disagree ({t1.status} vs {t2.status})")
    elif _ok(t1, threshold):
        # A confident check beats an unconfident or invalid one.
        chosen, tier = t1, "1" if t2 is None or not _ok(t2, threshold) else "1+2"
    elif _ok(t2, threshold):
        # The escalation's purpose: a confident Tier 2 settles a low-confidence Tier 1.
        chosen, tier = t2, "2"
    else:
        best = max((v for v in (t1, t2) if v is not None), key=lambda v: v.confidence)
        why = (
            "; ".join(best.problems)
            if not best.valid
            else (f"confidence {best.confidence:.2f} below {threshold}")
        )
        return pending(why)

    if not explanation_ok:
        return pending("explanation missing or its citations did not check out")
    silent = chosen.status == "walked_back" and chosen.walked_back_kind == "silent"
    label = DISPLAY[chosen.status] + (" (silent)" if silent else "")
    return Decision(chosen.status, label, True, silent, "passed all checks", tier)


def needs_tier2(t1: Verdict | None, threshold: float = DEFAULT_THRESHOLD) -> bool:
    """Escalate: invalid or low-confidence Tier 1 results, and every walk-back (2nd check).

    Not when Tier 1 names a rubric pending condition: the item is held as pending
    whatever a second check says, so paying for one changes nothing.
    """
    if t1 is not None and t1.valid and t1.pending_reason != "none":
        return False
    return t1 is None or not t1.valid or t1.confidence < threshold or t1.status == "walked_back"


# ---------- the reason shown on a pending item's public page ----------
# `Decision.reason` is internal: it names draft statuses ("checks disagree (walked_back/
# explicit vs delivered/none)"), field names and confidence scores, and it stays in
# final_status and `aipb status` for the audit. The site shows only these sentences. None
# names a draft status, a figure or a direction, so a pending page never hints at a verdict
# that wasn't published. Anything not listed gets the general sentence.
PUBLIC_REASONS: tuple[tuple[str, str], ...] = (
    ("open error report", "A possible error was reported, and it is being reviewed."),
    ("not verified yet", "It hasn't been checked against later filings yet."),
    (
        "rubric: vague deliverable",
        "The promise doesn't name a specific enough product, feature or program to check.",
    ),
    (
        "rubric: run rate or realized unclear",
        "The promise doesn't say whether its target is a run rate or an amount actually realized.",
    ),
    (
        "rubric: basis changed",
        "The company changed how it reports this measure, so later figures can't be "
        "compared directly.",
    ),
    (
        "rubric: undefined base",
        "The promise doesn't say what its percentage is measured against.",
    ),
    ("confidence ", "Later filings don't show clearly enough what happened."),
    ("checks disagree", "Two independent checks didn't reach the same status."),
    (
        "walked back needs two confident checks",
        "Two independent checks didn't reach the same status.",
    ),
    (
        "explanation missing or its citations did not check out",
        "The written explanation didn't pass the citation and wording checks.",
    ),
    (
        "explanation was written for a different status",
        "The written explanation is out of date and is being redone.",
    ),
    (
        "the reported revenue growth for the deadline year",  # targets.GROWTH_HOLD (D57)
        "The reported revenue growth for the deadline year needs a closer look against "
        "the promised target.",
    ),
)
PUBLIC_REASON_OTHER = "The check of later filings didn't produce a result that could be published."


def public_reason(reason: str | None) -> str:
    """The plain-language sentence for a pending item's page (D58)."""
    r = (reason or "not verified yet").strip()
    for prefix, text in PUBLIC_REASONS:
        if r.startswith(prefix):
            return text
    return PUBLIC_REASON_OTHER
