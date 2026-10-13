"""Strongest disposition frozen evidence permits; agent proposals cannot exceed it.

Pure and vendor-free: inputs are already admitted per run by adapters (receipts,
native JUnit classification, separately captured witnesses, environment and
sandbox observations). Test claims stay claims; these gates only refuse to let
them support more than the investigation contract allows.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Sha256 = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
TestId = Annotated[str, Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9_./:#\[\]-]+$')]
Token = Annotated[str, Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9_.:-]+$')]

Execution = Literal['completed', 'blocked', 'failed', 'unknown', 'unsupported']
Finding = Literal['reproduced', 'not_reproduced', 'refuted_in_scope', 'inconclusive']
Fix = Literal['verified', 'not_verified', 'not_applicable']
Revision = Literal['baseline', 'candidate']


class _Frozen(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)


class ExpectedFailure(_Frozen):
    """The planned security assertion, located in the frozen patch."""
    exception_type: Token
    path: str = Field(min_length=1, max_length=256)
    function: Token
    assertion_lines: tuple[Annotated[int, Field(ge=1)], ...] = Field(min_length=1)


class ObservationPlan(_Frozen):
    """Typed expectations from the reviewed plan and frozen patch; never model text."""
    control_test_id: TestId
    security_test_id: TestId
    expected_failure: ExpectedFailure
    expected_safe_behavior: Token
    frozen_patch_sha256: Sha256

    @model_validator(mode='after')
    def distinct_tests(self):
        if self.control_test_id == self.security_test_id:
            raise ValueError('Control and security tests must be distinct')
        return self


class ClassifiedFailure(_Frozen):
    """Bounded native failure element; None marks a field the runner could not classify."""
    exception_type: Token | None
    path: str | None = Field(default=None, max_length=256)
    function: Token | None = None
    line: Annotated[int, Field(ge=1)] | None = None


class ObservedOutcome(_Frozen):
    test_id: TestId
    outcome: Literal['passed', 'failed', 'skipped', 'error']
    failure: ClassifiedFailure | None = None

    @model_validator(mode='after')
    def failure_only_when_failed(self):
        if self.outcome != 'failed' and self.failure is not None:
            raise ValueError('Only a failed test carries a failure classification')
        return self


class Witness(_Frozen):
    """Planned observable captured as its own artifact, outside the pass/fail claim."""
    artifact_sha256: Sha256
    path_reached: bool | None
    effect: Literal['observed', 'absent', 'unknown']
    safe_behavior: Token | None = None


class EnvironmentIdentity(_Frozen):
    image_digest: Sha256
    recipe_sha256: Sha256
    dependency_inventory_sha256: Sha256
    policy_revision: Token
    limits_sha256: Sha256


class SandboxEvent(_Frozen):
    kind: Literal['policy_denial', 'resource_limit']
    phase: Literal['setup', 'test']
    touches_witness_path: bool | None


class RunEvidence(_Frozen):
    """One fresh execution of the frozen patch on one revision."""
    delivery: Literal['not_dispatched', 'unknown', 'acknowledged']
    completion: Literal['unknown', 'terminal_observed']
    execution_failure: Literal['timeout', 'build', 'dependency', 'discovery', 'transport',
                               'policy', 'sandbox', 'unknown'] | None = None
    patch_sha256: Sha256
    discovered_test_ids: tuple[TestId, ...]
    outcomes: tuple[ObservedOutcome, ...]
    witness: Witness | None
    environment: EnvironmentIdentity
    sandbox_events: tuple[SandboxEvent, ...] = ()


class AssessmentEvidence(_Frozen):
    plan: ObservationPlan
    baseline: tuple[RunEvidence, ...] = Field(min_length=1)
    candidate: tuple[RunEvidence, ...] = ()


class Disposition(_Frozen):
    execution: Execution
    finding: Finding
    fix: Fix


RunClass = Literal['reproduces', 'safe', 'control_failed', 'unusable']
LimitationCode = Literal[
    'delivery_unknown', 'execution_failed', 'execution_blocked', 'patch_mismatch',
    'discovery_mismatch', 'test_skipped', 'test_error', 'control_failed',
    'unplanned_failure', 'unclassified_failure', 'witness_missing', 'witness_unsupported',
    'sandbox_attributed', 'sandbox_event_recorded', 'contradiction', 'no_valid_run',
    'incomplete_repeats', 'baseline_not_reproduced', 'environment_mismatch',
    'candidate_not_safe']


class Limitation(_Frozen):
    code: LimitationCode
    revision: Revision | None = None
    run: int | None = None


class RunAssessment(_Frozen):
    revision: Revision
    run: int
    execution: Execution
    classification: RunClass


class GateResult(_Frozen):
    permitted: Disposition
    runs: tuple[RunAssessment, ...]
    limitations: tuple[Limitation, ...]


class Admission(_Frozen):
    admitted: bool
    disposition: Disposition
    rejections: tuple[str, ...]


def _assess_run(plan: ObservationPlan, revision: Revision, index: int, run: RunEvidence):
    notes: list[Limitation] = []

    def note(code):
        notes.append(Limitation(code=code, revision=revision, run=index))

    if run.delivery != 'acknowledged' or run.completion != 'terminal_observed':
        note('delivery_unknown')
        return RunAssessment(revision=revision, run=index, execution='unknown',
                             classification='unusable'), notes
    if run.execution_failure is not None:
        blocked = run.execution_failure in ('policy', 'sandbox')
        unknown = run.execution_failure == 'unknown'
        note('execution_blocked' if blocked else 'execution_failed')
        return RunAssessment(revision=revision, run=index,
                             execution='unknown' if unknown else 'blocked' if blocked else 'failed',
                             classification='unusable'), notes

    planned = (plan.control_test_id, plan.security_test_id)
    by_id = {outcome.test_id: outcome for outcome in run.outcomes}
    if run.patch_sha256 != plan.frozen_patch_sha256:
        note('patch_mismatch')
    if (sorted(run.discovered_test_ids) != sorted(planned) or len(by_id) != len(run.outcomes)
            or set(by_id) != set(planned)):
        note('discovery_mismatch')
    if any(o.outcome == 'skipped' for o in run.outcomes):
        note('test_skipped')
    if any(o.outcome == 'error' for o in run.outcomes):
        note('test_error')
    if notes:
        return RunAssessment(revision=revision, run=index, execution='failed',
                             classification='unusable'), notes

    attributed = False
    for event in run.sandbox_events:
        if event.phase == 'test' and event.touches_witness_path is not False:
            attributed = True
        else:
            note('sandbox_event_recorded')
    if attributed:
        note('sandbox_attributed')
        return RunAssessment(revision=revision, run=index, execution='blocked',
                             classification='unusable'), notes

    def done(classification):
        return RunAssessment(revision=revision, run=index, execution='completed',
                             classification=classification), notes

    if by_id[plan.control_test_id].outcome != 'passed':
        note('control_failed')
        return done('control_failed')
    security, witness = by_id[plan.security_test_id], run.witness
    if security.outcome == 'failed':
        failure, expected = security.failure, plan.expected_failure
        if (failure is None or None in (failure.exception_type, failure.path,
                                        failure.function, failure.line)):
            note('unclassified_failure')
            return done('unusable')
        if (failure.exception_type != expected.exception_type or failure.path != expected.path
                or failure.function != expected.function
                or failure.line not in expected.assertion_lines):
            note('unplanned_failure')
            return done('unusable')
        if witness is None or witness.effect != 'observed' or witness.path_reached is False:
            note('witness_missing' if witness is None or witness.effect == 'unknown'
                 else 'witness_unsupported')
            return done('unusable')
        return done('reproduces')
    if (witness is None or witness.path_reached is None or witness.effect == 'unknown'
            or witness.safe_behavior is None):
        note('witness_missing')
        return done('unusable')
    if (witness.path_reached is not True or witness.effect != 'absent'
            or witness.safe_behavior != plan.expected_safe_behavior):
        note('witness_unsupported')
        return done('unusable')
    return done('safe')


_EXECUTION_ORDER = ('unknown', 'blocked', 'failed', 'completed')


def assess(evidence: AssessmentEvidence) -> GateResult:
    """Total and deterministic: identical evidence always yields the same result."""
    runs: list[RunAssessment] = []
    limitations: list[Limitation] = []
    for revision, revision_runs in (('baseline', evidence.baseline), ('candidate', evidence.candidate)):
        for index, run in enumerate(revision_runs):
            assessment, notes = _assess_run(evidence.plan, revision, index, run)
            runs.append(assessment)
            limitations.extend(notes)
    baseline = [r for r in runs if r.revision == 'baseline']
    candidate = [r for r in runs if r.revision == 'candidate']

    def classes(revision_runs):
        return {r.classification for r in revision_runs}

    # Finding depends only on the baseline. Incomplete repeats are recorded but do
    # not erase a valid reproduction; failed controls and contrary valid runs block it.
    base = classes(baseline)
    finding: Finding = 'inconclusive'
    if 'control_failed' in base:
        pass
    elif {'reproduces', 'safe'} <= base:
        limitations.append(Limitation(code='contradiction', revision='baseline'))
    elif 'reproduces' in base:
        finding = 'reproduced'
        if 'unusable' in base:
            limitations.append(Limitation(code='incomplete_repeats', revision='baseline'))
    elif base == {'safe'}:
        finding = 'not_reproduced'
    elif 'safe' in base:
        limitations.append(Limitation(code='incomplete_repeats', revision='baseline'))
    else:
        limitations.append(Limitation(code='no_valid_run', revision='baseline'))

    fix: Fix = 'not_applicable'
    if evidence.candidate:
        fix = 'not_verified'
        cand = classes(candidate)
        if {'reproduces', 'safe'} <= cand:
            limitations.append(Limitation(code='contradiction', revision='candidate'))
        environments = {run.environment for run in evidence.baseline + evidence.candidate}
        comparable = len(environments) == 1
        if not comparable:
            limitations.append(Limitation(code='environment_mismatch'))
        # An incomplete baseline repeat preserves the finding but cannot verify the fix.
        if finding != 'reproduced' or base != {'reproduces'}:
            limitations.append(Limitation(code='baseline_not_reproduced', revision='candidate'))
        elif cand != {'safe'}:
            limitations.append(Limitation(code='candidate_not_safe', revision='candidate'))
        elif comparable:
            fix = 'verified'

    execution = min((r.execution for r in runs), key=_EXECUTION_ORDER.index)
    return GateResult(permitted=Disposition(execution=execution, finding=finding, fix=fix),
                      runs=tuple(runs), limitations=tuple(limitations))


def admit(proposal: Disposition, result: GateResult) -> Admission:
    """Admit a proposal equal to, or weaker than, what the evidence permits."""
    permitted, rejections = result.permitted, []
    if proposal.execution != permitted.execution:
        rejections.append(f'execution {proposal.execution} differs from observed {permitted.execution}')
    if proposal.finding == 'refuted_in_scope':
        rejections.append('refuted_in_scope needs affirmative evidence these gates cannot admit')
    elif proposal.finding not in (permitted.finding, 'inconclusive'):
        rejections.append(f'finding {proposal.finding} exceeds permitted {permitted.finding}')
    if 'not_applicable' in (proposal.fix, permitted.fix):
        if proposal.fix != permitted.fix:
            rejections.append(f'fix {proposal.fix} conflicts with permitted {permitted.fix}')
    elif proposal.fix not in (permitted.fix, 'not_verified'):
        rejections.append(f'fix {proposal.fix} exceeds permitted {permitted.fix}')
    elif proposal.fix == 'verified' and proposal.finding != 'reproduced':
        rejections.append('fix verified requires a reproduced baseline finding')
    return Admission(admitted=not rejections, disposition=proposal if not rejections else permitted,
                     rejections=tuple(rejections))
