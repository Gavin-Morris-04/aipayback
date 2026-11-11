"""The only LLM-written part of an issue: a 2-3 sentence intro, fact-checked by code.

Every number, ticker, company name and status in the intro must appear in the issue's
facts. On a mismatch the intro is regenerated once (with the problems named); if that
also fails, or the budget or key is missing, the issue uses the template intro.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal

from aipb.budget.guard import BudgetError
from aipb.context import AppContext
from aipb.llm.client import MissingApiKey, OfflineCacheMiss
from aipb.llm.params import build_params, load_prompt, stage_settings
from aipb.newsletter.issue import Issue, template_intro
from aipb.verify.neutral import banned_words

STAGE = "newsletter_intro"
STATUS_WORDS = ("Delivered", "On track", "No evidence yet", "Walked back")
NOT_TICKERS = {"AI", "SEC", "US", "USA", "CEO", "CFO", "IT", "OK", "GAAP", "XBRL", "EX"}


def allowed_numbers(facts: dict) -> set[str]:
    text = json.dumps(facts)
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


def fact_check(text: str, facts: dict, all_companies: list[str]) -> list[str]:
    problems = []
    nums = allowed_numbers(facts)
    for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text):
        if n.replace(",", "") not in nums:
            problems.append(f"number {n} is not in the facts")
    tickers = {i["ticker"] for i in facts["items"]}
    for t in re.findall(r"\b[A-Z]{2,5}\b", text):
        if t not in tickers and t not in NOT_TICKERS:
            problems.append(f"ticker-like word {t} is not in the facts")
    names = {i["company"] for i in facts["items"]}
    for name in all_companies:
        if name not in names and name in text:
            problems.append(f"mentions {name}, which is not in this issue")
    statuses = {i["status"] for i in facts["items"]} | {
        k for k, v in facts.get("by_status", {}).items() if v
    }
    for s in STATUS_WORDS:
        if s.lower() in text.lower() and not any(s.lower() in x.lower() for x in statuses):
            problems.append(f"status '{s}' is not in the facts")
    if words := banned_words(text):
        problems.append(f"non-neutral wording: {words}")
    if len(text) > 700:
        problems.append("intro is too long")
    return problems


def write_intro(
    ctx: AppContext, issue: Issue, all_companies: list[str], *, max_usd: Decimal
) -> Issue:
    """Fill issue.intro: the LLM intro if it passes the fact check, else the template."""
    issue.intro, issue.intro_source = template_intro(issue), "template"
    try:
        cfg = stage_settings(ctx.stages, STAGE, None)
        prompt = load_prompt(ctx.paths.prompts_dir, STAGE, cfg["prompt"])
    except (KeyError, FileNotFoundError) as exc:
        issue.notes.append(f"intro: {exc}; template used")
        return issue
    feedback = ""
    for attempt in (1, 2):
        user = "Facts:\n" + json.dumps(issue.facts, indent=1, sort_keys=True)
        if feedback:
            user += f"\n\nYour previous intro failed the fact check: {feedback}. Fix it."
        params = build_params(cfg, prompt, user)
        estimate = ctx.estimator.worst_case_cost(ctx.pricing, params, batch=False)
        if estimate > max_usd:
            issue.notes.append(f"intro estimate {estimate} is over the {max_usd} cap; template")
            return issue
        try:
            with ctx.guard.start_run(
                command="newsletter-intro", stage=STAGE, estimate=estimate, confirm=False
            ) as run:
                res = ctx.llm.create(
                    run=run, stage=STAGE, prompt_version=prompt.id, params=params, shard=issue.key
                )
        except (BudgetError, MissingApiKey, OfflineCacheMiss) as exc:
            issue.notes.append(f"intro: {type(exc).__name__}; template used")
            return issue
        text = res.text().strip() if res.status == "ok" else ""
        problems = fact_check(text, issue.facts, all_companies) if text else ["no text"]
        if not problems:
            issue.intro, issue.intro_source = text, "llm"
            return issue
        feedback = "; ".join(problems)
        issue.notes.append(f"intro attempt {attempt} rejected: {feedback}")
    return issue
