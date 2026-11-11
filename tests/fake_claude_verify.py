"""Fake answers for Phase 3 requests: Tier 1 verdicts, the Tier 2 tool loop, explanations.

Defaults: a promise whose deadline hasn't passed and that has later evidence is
"on_track" (cites E1); otherwise "no_evidence_yet". Tests override with fake.t1 / fake.t2
(callables that take the user text and return a verdict dict or None).
"""

from __future__ import annotations

import json
import re

T1_MARK = "You check whether a public company's AI promise"
T2_MARK = "You are the second, independent check"
EXPLAIN_MARK = "You write the short explanation"


def default_verdict(user: str) -> dict:
    evidence = re.findall(r'<evidence id="(E\d+)"', user)
    passed = re.search(r"Deadline passed as of [^:]+: yes", user)
    if evidence and not passed:
        return {
            "status": "on_track",
            "walked_back_kind": "none",
            "confidence": 0.86,
            "evidence_ids": [evidence[0]],
            "number_ids": [],
            "key_finding": "A later 10-Q reports progress toward this target.",
        }
    return {
        "status": "no_evidence_yet",
        "walked_back_kind": "none",
        "confidence": 0.9,
        "evidence_ids": [],
        "number_ids": [],
        "key_finding": "No later filing in this data reports a figure for this target.",
    }


def _user_text(params: dict) -> str:
    first = params["messages"][0]["content"]
    if isinstance(first, str):
        return first
    return " ".join(b.get("text", "") for b in first if b.get("type") == "text")


def answer(fake, params: dict, msg_cls):
    system = " ".join(b.get("text", "") for b in params.get("system", []))
    model = params.get("model", "claude-haiku-5-5")
    if T1_MARK in system:
        user = _user_text(params)
        v = (fake.t1(user) if getattr(fake, "t1", None) else None) or default_verdict(user)
        return msg_cls(json.dumps(v), model=model)
    if T2_MARK in system:
        user = _user_text(params)
        turns = sum(1 for m in params["messages"] if m["role"] == "assistant")
        if turns == 0:
            block = {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "search_company_filings",
                "input": {"query": "revenue software savings"},
            }
            return msg_cls("", model=model, content=[block], stop_reason="tool_use")
        v = (fake.t2(user) if getattr(fake, "t2", None) else None) or default_verdict(user)
        block = {
            "type": "tool_use",
            "id": f"toolu_{turns + 1}",
            "name": "submit_verdict",
            "input": v,
        }
        return msg_cls("", model=model, content=[block], stop_reason="tool_use")
    if EXPLAIN_MARK in system:
        docs = [b for b in params["messages"][0]["content"] if b.get("type") == "document"]
        blocks = []
        for i, d in enumerate(docs[:2]):
            data = d["source"]["data"]
            end = data.find(". ") + 1 if ". " in data else len(data)
            cited = data[:end]
            lead = "The company stated a target" if i == 0 else "A later filing reports"
            blocks.append(
                {
                    "type": "text",
                    "text": f"{lead}.",
                    "citations": [
                        {
                            "type": "char_location",
                            "cited_text": cited,
                            "document_index": i,
                            "document_title": d["title"],
                            "start_char_index": 0,
                            "end_char_index": end,
                        }
                    ],
                }
            )
            blocks.append({"type": "text", "text": " "})
        if getattr(fake, "explain_bad_word", False):
            blocks.append({"type": "text", "text": "Management failed to deliver."})
        return msg_cls("", model=model, content=blocks)
    return None
