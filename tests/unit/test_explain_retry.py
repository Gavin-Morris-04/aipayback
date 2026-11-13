"""Explanation retry (D53): same request, plus a note naming the failed checks."""

from aipb.stages.explain import retry_params


def test_retry_adds_the_failed_checks_and_leaves_the_original_alone():
    doc = {"type": "document", "source": {"type": "text", "data": "x"}, "title": "Promise"}
    params = {
        "model": "claude-haiku-5-5",
        "messages": [{"role": "user", "content": [doc, {"type": "text", "text": "Write it."}]}],
    }
    problems = ["wording: the company's voice outside quotation marks: we expect", "x\n  y"]
    retry = retry_params(params, problems)
    blocks = retry["messages"][0]["content"]
    assert blocks[:2] == params["messages"][0]["content"]  # documents and ask unchanged
    note = blocks[-1]["text"]
    assert "company's voice outside quotation marks" in note and "- x y" in note
    assert "third person" in note
    assert len(params["messages"][0]["content"]) == 2  # the original isn't mutated
    assert len(retry["messages"]) == 1  # a fresh single-turn request, nothing replayed
