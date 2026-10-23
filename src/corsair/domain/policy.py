"""Pure stopping/verdict rules; no model, sandbox or storage effects."""

from __future__ import annotations

from collections.abc import Sequence

from corsair.domain.verification import Evaluation, Fix, Gate, GateVerdict, Label, Verdict


def negative_verdict(evaluations: Sequence[Evaluation], threshold: int) -> Verdict | None:
    """K4: LIKELY_NOT_EXPLOITABLE once ``threshold`` distinct submissions were clean negatives, and no submission was
    decisive. Distinct by submission digest, so resubmitting one probe counts once. A LIKELY_EXPLOITABLE evaluation
    always wins over the negatives. The fix is not verified for a negative label (fix=not_applicable)."""
    if threshold < 1:
        raise ValueError("the negative threshold is at least 1")
    if any(e.verdict is not None for e in evaluations):
        return None
    observed: dict[str, Evaluation] = {}
    for evaluation in evaluations:
        if evaluation.clean_negative:
            observed.setdefault(evaluation.submission_sha256, evaluation)
    if len(observed) < threshold:
        return None
    counted = tuple(observed.values())
    return Verdict(
        label=Label.LIKELY_NOT_EXPLOITABLE,
        rule="K4",
        fix=Fix.NOT_APPLICABLE,
        fix_reason="fix verification is not run for a negative label",
        reason=f"{len(counted)} distinct submission(s) were clean negatives (threshold {threshold}): control "
        "held and EXPLOIT_PAYLOAD held on the vulnerable revision, both runs executing the target "
        "lines, and each probe passed the blind audit where one is configured",
        runs=tuple(run for e in counted for run in e.runs),
    )


def terminal_verdict(last: GateVerdict | None, attempts: int) -> Verdict:
    """The verdict when the producer stopped without a verified submission: decided from the last gate it hit."""
    if last is None:
        return Verdict(
            label=Label.ERROR, rule="K0", reason="no submission was evaluated", fix=Fix.NOT_APPLICABLE
        )
    if last.stage is Gate.INFRA:
        return Verdict(label=Label.ERROR, rule="K0", reason=last.reason, fix=Fix.NOT_APPLICABLE)
    if last.stage is Gate.BUILD_REPLAY:
        return Verdict(label=Label.UNABLE_TO_RUN, rule="K2", reason=last.reason, fix=Fix.NOT_APPLICABLE)
    reason = f"after {attempts} submission(s) the last one failed {last.stage}: {last.reason}"
    return Verdict(label=Label.INCONCLUSIVE, rule="K3", reason=reason[:2000], fix=Fix.NOT_APPLICABLE)
