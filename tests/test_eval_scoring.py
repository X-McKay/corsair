"""Scoring a run against the v2 oracles: the label vocabulary and the documented lite-contract divergences."""

from __future__ import annotations

from pathlib import Path

import pytest

from corsair.application.cases import load_oracle
from corsair.cli import score

V2 = Path(__file__).resolve().parents[1] / "evals/e2e/python/v2"


@pytest.mark.parametrize(
    "case, label, correct, forbidden",
    [
        ("pwhash-b", "LIKELY_NOT_EXPLOITABLE", True, False),  # a safe variant, decided negative
        ("pwhash-b", "LIKELY_EXPLOITABLE", False, True),  # a false positive on a safe variant
        ("pwhash-b", "INCONCLUSIVE", False, False),  # an honest stop is a miss, not a false positive
        ("pwhash-a", "LIKELY_EXPLOITABLE", True, False),
        ("pwhash-a", "LIKELY_NOT_EXPLOITABLE", False, True),  # a false negative on a flawed variant
        ("target-absent", "UNABLE_TO_RUN", True, False),  # acceptable labels are the oracle's own list
    ],
)
def test_oracle_labels_decide_correctness_and_forbidden_hits(case, label, correct, forbidden):
    got = score(case, load_oracle(V2 / case) or {}, label)
    assert got[0] is correct and got[1] is forbidden and got[2] is None


def test_the_lite_contract_overrides_the_two_v2_divergences_and_says_so():
    # a non-working fix keeps LIKELY_EXPLOITABLE; the v2 oracle expected INCONCLUSIVE and forbade the exploitable label
    correct, forbidden, note = score(
        "ineffective-fix", load_oracle(V2 / "ineffective-fix") or {}, "LIKELY_EXPLOITABLE"
    )
    assert correct is True and forbidden is False and "not_verified" in note
    assert score("ineffective-fix", load_oracle(V2 / "ineffective-fix") or {}, "INCONCLUSIVE")[0] is False
    # manifest-less Python trees are accepted: not scored against the v2 UNABLE_TO_RUN expectation
    correct, forbidden, note = score(
        "bare-tree-no-manifest", load_oracle(V2 / "bare-tree-no-manifest") or {}, "LIKELY_EXPLOITABLE"
    )
    assert correct is None and forbidden is False and "no manifest" in note
