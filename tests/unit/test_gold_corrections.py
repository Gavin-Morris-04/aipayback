"""Gold corrections: applied on top of Nick's labels, every quote checked verbatim."""

import pytest

from aipb.evals.corrections import CorrectionError, apply
from aipb.evals.run import GoldPassage

TEXT = (
    "We shipped new AI PCs, with Copilot+ capabilities anticipated next quarter. "
    "We plan to build the world’s fastest AI supercomputer."
)


def gold(label="none", promises=None, pid="p1"):
    return GoldPassage(pid, "NVDA", label, "keyword", TEXT, promises or [])


def test_relabel_and_add_a_promise():
    out = apply(
        [gold()],
        [
            {
                "passage_id": "p1",
                "source": "N7 row 11",
                "reason": "model was right",
                "set_label": "promise",
                "add_promises": [
                    {
                        "quote": "with Copilot+ capabilities anticipated next quarter",
                        "claim_type": "product_or_timeline",
                        "deadline": "next quarter",
                    }
                ],
            }
        ],
    )
    assert out[0].label == "promise"
    assert out[0].promises[0]["quote"] == "with Copilot+ capabilities anticipated next quarter"


def test_fix_a_quote_to_the_filings_characters():
    wrong = {"quote": "the world's fastest AI supercomputer", "claim_type": "other"}
    out = apply(
        [gold("promise", [wrong])],
        [
            {
                "passage_id": "p1",
                "source": "N7",
                "reason": "curly apostrophe",
                "fix_quotes": [
                    {
                        "from": "the world's fastest AI supercomputer",
                        "to": "the world’s fastest AI supercomputer",
                    }
                ],
            }
        ],
    )
    assert out[0].promises[0]["quote"] == "the world’s fastest AI supercomputer"


def test_exclude_leaves_a_passage_out_and_other_splits_are_skipped():
    corr = [
        {"passage_id": "p1", "source": "N7", "reason": "pending", "exclude": True},
        {"passage_id": "not-here", "source": "N7", "reason": "test company", "exclude": True},
    ]
    out = apply([gold(), gold(pid="p2")], corr)
    assert [g.passage_id for g in out] == ["p2"]


def test_a_quote_not_in_the_passage_is_refused():
    corr = [
        {
            "passage_id": "p1",
            "source": "N7",
            "reason": "x",
            "add_promises": [{"quote": "AI revenue will double", "claim_type": "revenue"}],
        }
    ]
    with pytest.raises(CorrectionError, match="not verbatim"):
        apply([gold()], corr)


def test_every_correction_needs_a_source_and_reason():
    with pytest.raises(CorrectionError, match="source and a reason"):
        apply([gold()], [{"passage_id": "p1", "exclude": True}])
