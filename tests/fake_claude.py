"""A fake Anthropic SDK for stage tests: messages.create and messages.batches.*.

It answers like a sensible model, from simple rules over the request text, so the filter,
extract and verify stages can be tested end to end without the network or a key. Knobs:
- paraphrase_first: the first extract answer for a passage misquotes one statement
  (exercises the verbatim check and the one-retry path);
- refuse: substrings; a request containing one gets stop_reason "refusal".
"""

from __future__ import annotations

import itertools
import json
import re
from collections.abc import Callable
from types import SimpleNamespace

PROMISE_CUES = re.compile(r"\b(expect|expects|plan|plans|will|target|aim)\b", re.I)
AI = re.compile(r"\bAI\b|artificial intelligence|generative|machine learning")
NUMBER = re.compile(r"\$?\d[\d,.]*\s*(million|billion|percent)?")


class Msg:
    def __init__(self, text: str, *, stop_reason: str = "end_turn", in_tok: int = 1000,
                 out_tok: int = 100, model: str = "claude-haiku-5-5") -> None:  # fmt: skip
        self.text = text
        self.stop_reason = stop_reason
        self.model = model
        self.usage = SimpleNamespace(
            input_tokens=in_tok, output_tokens=out_tok, cache_read_input_tokens=0,
            cache_creation_input_tokens=0, cache_creation=None, output_tokens_details=None,
        )  # fmt: skip

    def model_dump(self, mode: str = "json") -> dict:
        return {
            "id": "msg_fake", "type": "message", "role": "assistant", "model": self.model,
            "content": [{"type": "text", "text": self.text}], "stop_reason": self.stop_reason,
            "usage": {"input_tokens": self.usage.input_tokens,
                      "output_tokens": self.usage.output_tokens},
        }  # fmt: skip


def _system(params: dict) -> str:
    sys = params.get("system", "")
    if isinstance(sys, list):
        return " ".join(b.get("text", "") for b in sys)
    return sys


def _last_user(params: dict) -> str:
    for m in reversed(params["messages"]):
        if m["role"] == "user":
            c = m["content"]
            return c if isinstance(c, str) else " ".join(b.get("text", "") for b in c)
    return ""


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|(?<=[.!?][”\"])\s+|\n{2,}", text)
    return [s.strip() for s in parts if s and s.strip()]


def classify(text: str) -> tuple[str, str]:
    for s in _sentences(text):
        if AI.search(s) and PROMISE_CUES.search(s):
            return ("promise", "high") if NUMBER.search(s) else ("hype", "low")
    return "none", "high"


def extract(text: str) -> list[dict]:
    out = []
    for s in _sentences(text):
        if not (AI.search(s) and PROMISE_CUES.search(s)):
            continue
        quote = s.rstrip(".")
        has_num = bool(NUMBER.search(s))
        year = re.search(r"\b(20\d\d)\b", s)
        out.append({
            "quote": quote, "kind": "promise" if has_num else "hype",
            "claim_type": "cost_savings" if "saving" in s else "other",
            "metric": "annual run-rate cost savings" if "saving" in s else None,
            "target_text": (m.group(0).strip() if (m := NUMBER.search(s)) else None),
            "target_value": None, "target_unit": None, "baseline": None,
            "deadline_text": None, "deadline_year": int(year.group(1)) if year else None,
            "deadline_precision": "year" if year else "none",
            "specificity": 3 if has_num and year else 1, "confidence": "high",
        })  # fmt: skip
    return out


class FakeClaude:
    def __init__(
        self,
        api_key: str = "test",
        *,
        paraphrase_first: bool = False,
        refuse: tuple[str, ...] = (),
        responder: Callable[[dict], Msg] | None = None,
    ) -> None:
        self.api_key = api_key
        self.calls: list[dict] = []
        self.batches: dict[str, list[dict]] = {}
        self.retrieves = 0
        self.paraphrase_first = paraphrase_first
        self.refuse = refuse
        self.responder = responder
        self._ids = itertools.count(1)
        self.messages = SimpleNamespace(
            create=self._create,
            batches=SimpleNamespace(
                create=self._batch_create, retrieve=self._batch_retrieve,
                results=self._batch_results,
            ),
        )  # fmt: skip

    # ------------------------------------------------------------------ answers

    def answer(self, params: dict) -> Msg:
        if self.responder:
            return self.responder(params)
        user = _last_user(params)
        if any(r in user for r in self.refuse):
            return Msg("", stop_reason="refusal")
        system = _system(params)
        model = params.get("model", "claude-haiku-5-5")
        if "You screen passages" in system:
            items = []
            for pid, body in re.findall(r'<passage id="(P\d+)"[^>]*>\n(.*?)\n</passage>', user,
                                        re.S):  # fmt: skip
                label, conf = classify(body)
                items.append({"id": pid, "label": label, "confidence": conf})
            return Msg(json.dumps({"items": items}), model=model)
        if "You extract forward-looking statements" in system:
            if "are not exact substrings" in user:  # the retry turn: quote exactly
                first_user = params["messages"][0]["content"]
                body = re.search(r"<passage>\n(.*)\n</passage>", first_user, re.S).group(1)
                return Msg(json.dumps({"statements": extract(body)}), model=model)
            body = re.search(r"<passage>\n(.*)\n</passage>", user, re.S).group(1)
            sts = extract(body)
            if self.paraphrase_first and sts:
                sts[0] = {**sts[0], "quote": sts[0]["quote"].replace("expect", "anticipate")}
            return Msg(json.dumps({"statements": sts}), model=model)
        return Msg("OK", model=model)

    # ------------------------------------------------------------------ SDK surface

    def _create(self, **params):
        self.calls.append(params)
        return self.answer(params)

    def _batch_create(self, requests):
        bid = f"msgbatch_{next(self._ids):04d}"
        self.batches[bid] = list(requests)
        return SimpleNamespace(id=bid, processing_status="in_progress")

    def _batch_retrieve(self, batch_id):
        self.retrieves += 1
        return SimpleNamespace(id=batch_id, processing_status="ended")

    def _batch_results(self, batch_id):
        for req in reversed(self.batches[batch_id]):  # any order, like the real API
            self.calls.append(req["params"])
            msg = self.answer(req["params"])
            yield SimpleNamespace(
                custom_id=req["custom_id"],
                result=SimpleNamespace(type="succeeded", message=msg),
            )


def factory(fake: FakeClaude):
    def make(api_key: str, **_kw) -> FakeClaude:
        fake.api_key = api_key
        return fake

    return make
