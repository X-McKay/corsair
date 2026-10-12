"""Table-driven disposition gates over SPEC-0018-shaped synthetic evidence; no live runs."""
import hashlib

import pytest
from pydantic import ValidationError

from corsair.core.disposition import (AssessmentEvidence, ClassifiedFailure, Disposition,
                                      EnvironmentIdentity, ExpectedFailure, ObservationPlan,
                                      RunEvidence, SandboxEvent, ObservedOutcome, Witness, admit,
                                      assess)

TESTS = 'benchmarks/fixtures/path-traversal/test_documents.py'
CONTROL = f'{TESTS}::test_benign_control'
SECURITY = f'{TESTS}::test_security_rejects_outside_read'
# Frozen shared-test identity recorded in docs/qualification/native-two-test-fixture.md.
PATCH = 'c9ce06213661ad5f9b97ac64ee7ade81895d7566e090d72837cecc7ff9f07673'


def digest(label):
    return hashlib.sha256(label.encode()).hexdigest()


PLAN = ObservationPlan(
    control_test_id=CONTROL, security_test_id=SECURITY,
    expected_failure=ExpectedFailure(exception_type='AssertionError', path=TESTS,
                                     function='test_security_rejects_outside_read',
                                     assertion_lines=(64, 65, 66)),
    expected_safe_behavior='ValueError', frozen_patch_sha256=PATCH)
ENV = EnvironmentIdentity(image_digest=digest('image'), recipe_sha256=digest('recipe'),
                          dependency_inventory_sha256=digest('deps'),
                          policy_revision='policy-1', limits_sha256=digest('limits'))
PLANNED_FAILURE = ClassifiedFailure(exception_type='AssertionError', path=TESTS,
                                    function='test_security_rejects_outside_read', line=64)


def run(security='failed', *, control='passed', failure=PLANNED_FAILURE, witness='default', **changes):
    if witness == 'default':
        witness = (Witness(artifact_sha256=digest('open-audit'), path_reached=True, effect='observed')
                   if security == 'failed' else
                   Witness(artifact_sha256=digest('open-audit'), path_reached=True, effect='absent',
                           safe_behavior='ValueError'))
    values = dict(
        delivery='acknowledged', completion='terminal_observed', patch_sha256=PATCH,
        discovered_test_ids=(CONTROL, SECURITY),
        outcomes=(ObservedOutcome(test_id=CONTROL, outcome=control),
                  ObservedOutcome(test_id=SECURITY, outcome=security,
                              failure=failure if security == 'failed' else None)),
        witness=witness, environment=ENV)
    values.update(changes)
    return RunEvidence(**values)


REPRO, SAFE = run('failed'), run('passed')
OTHER_ENV = ENV.model_copy(update={'image_digest': digest('other-image')})
DENIED = (SandboxEvent(kind='policy_denial', phase='test', touches_witness_path=True),)


def codes(result):
    return {limitation.code for limitation in result.limitations}


CASES = {
    # name: (baseline runs, candidate runs, (execution, finding, fix), required limitation codes)
    'spec0018_reproduced_and_verified': ((REPRO,) * 3, (SAFE,) * 3, ('completed', 'reproduced', 'verified'), set()),
    'reproduced_without_candidate': ((REPRO,), (), ('completed', 'reproduced', 'not_applicable'), set()),
    'unrelated_baseline_exception': (
        (run(failure=PLANNED_FAILURE.model_copy(update={'exception_type': 'KeyError', 'path': 'documents.py',
                                                        'function': 'read_document', 'line': 3})),),
        (SAFE,), ('completed', 'inconclusive', 'not_verified'), {'unplanned_failure', 'baseline_not_reproduced'}),
    'precondition_assertion_not_planned': (
        (run(failure=PLANNED_FAILURE.model_copy(update={'line': 52})),), (SAFE,),
        ('completed', 'inconclusive', 'not_verified'), {'unplanned_failure'}),
    'unclassified_failure': ((run(failure=None),), (), ('completed', 'inconclusive', 'not_applicable'),
                             {'unclassified_failure'}),
    'missing_baseline_witness': ((run(witness=None),), (SAFE,), ('completed', 'inconclusive', 'not_verified'),
                                 {'witness_missing'}),
    'baseline_witness_without_effect': (
        (run(witness=Witness(artifact_sha256=digest('w'), path_reached=True, effect='absent')),), (),
        ('completed', 'inconclusive', 'not_applicable'), {'witness_unsupported'}),
    'baseline_witness_contradicts_itself': (
        (run(witness=Witness(artifact_sha256=digest('w'), path_reached=False, effect='observed')),), (),
        ('completed', 'inconclusive', 'not_applicable'), {'witness_unsupported'}),
    'sandbox_denied_candidate_rejection': ((REPRO,), (run('passed', sandbox_events=DENIED),),
                                           ('blocked', 'reproduced', 'not_verified'),
                                           {'sandbox_attributed', 'candidate_not_safe'}),
    'unknown_scope_sandbox_event_attributed': (
        (REPRO,), (run('passed', sandbox_events=(SandboxEvent(kind='resource_limit', phase='test',
                                                               touches_witness_path=None),)),),
        ('blocked', 'reproduced', 'not_verified'), {'sandbox_attributed'}),
    'unrelated_setup_event_recorded_only': (
        (REPRO,), (run('passed', sandbox_events=(SandboxEvent(kind='policy_denial', phase='setup',
                                                               touches_witness_path=True),)),),
        ('completed', 'reproduced', 'verified'), {'sandbox_event_recorded'}),
    'noncomparable_candidate_environment': ((REPRO,), (run('passed', environment=OTHER_ENV),),
                                            ('completed', 'reproduced', 'not_verified'), {'environment_mismatch'}),
    'contradictory_baseline_repeats': ((REPRO, SAFE, REPRO), (SAFE,), ('completed', 'inconclusive', 'not_verified'),
                                       {'contradiction'}),
    'contradictory_candidate_repeats': ((REPRO,), (SAFE, REPRO), ('completed', 'reproduced', 'not_verified'),
                                        {'contradiction', 'candidate_not_safe'}),
    'failed_control_blocks_finding': ((REPRO, run(control='failed')), (SAFE,),
                                      ('completed', 'inconclusive', 'not_verified'), {'control_failed'}),
    'failed_candidate_control': ((REPRO,), (run('passed', control='failed'),),
                                 ('completed', 'reproduced', 'not_verified'), {'control_failed'}),
    'skipped_security': ((run('skipped'),), (), ('failed', 'inconclusive', 'not_applicable'), {'test_skipped'}),
    'fixture_error': ((run('error'),), (), ('failed', 'inconclusive', 'not_applicable'), {'test_error'}),
    'compile_error': ((run(execution_failure='build', discovered_test_ids=(), outcomes=(), witness=None),), (),
                      ('failed', 'inconclusive', 'not_applicable'), {'execution_failed', 'no_valid_run'}),
    'third_test_discovered': ((run(discovered_test_ids=(CONTROL, SECURITY, f'{TESTS}::test_extra')),), (),
                              ('failed', 'inconclusive', 'not_applicable'), {'discovery_mismatch'}),
    'patch_digest_mismatch': ((REPRO,), (run('passed', patch_sha256=digest('other patch')),),
                              ('failed', 'reproduced', 'not_verified'), {'patch_mismatch'}),
    'unknown_delivery': ((run(delivery='unknown', completion='unknown'),), (),
                         ('unknown', 'inconclusive', 'not_applicable'), {'delivery_unknown'}),
    'timeout': ((run(execution_failure='timeout'),), (), ('failed', 'inconclusive', 'not_applicable'),
                {'execution_failed'}),
    'policy_blocked_execution': ((run(execution_failure='policy'),), (),
                                 ('blocked', 'inconclusive', 'not_applicable'), {'execution_blocked'}),
    'incomplete_repeat_preserves_reproduction': ((REPRO, run(execution_failure='timeout')), (SAFE,),
                                                 ('failed', 'reproduced', 'not_verified'),
                                                 {'incomplete_repeats', 'baseline_not_reproduced'}),
    'baseline_safe_is_not_reproduced': ((SAFE,) * 3, (SAFE,), ('completed', 'not_reproduced', 'not_verified'),
                                        {'baseline_not_reproduced'}),
    'safe_with_incomplete_repeat_is_inconclusive': ((SAFE, run(execution_failure='timeout')), (),
                                                    ('failed', 'inconclusive', 'not_applicable'),
                                                    {'incomplete_repeats'}),
    'candidate_pass_wrong_reason': (
        (REPRO,), (run('passed', witness=Witness(artifact_sha256=digest('w'), path_reached=True,
                                                   effect='absent', safe_behavior='PermissionError')),),
        ('completed', 'reproduced', 'not_verified'), {'witness_unsupported'}),
    'candidate_pass_path_not_reached': (
        (REPRO,), (run('passed', witness=Witness(artifact_sha256=digest('w'), path_reached=False,
                                                   effect='absent', safe_behavior='ValueError')),),
        ('completed', 'reproduced', 'not_verified'), {'witness_unsupported'}),
    'candidate_pass_without_witness': ((REPRO,), (run('passed', witness=None),),
                                       ('completed', 'reproduced', 'not_verified'), {'witness_missing'}),
}


@pytest.mark.parametrize('name', CASES)
def test_gate_permits_only_supported_disposition(name):
    baseline, candidate, expected, required = CASES[name]
    result = assess(AssessmentEvidence(plan=PLAN, baseline=baseline, candidate=candidate))
    assert (result.permitted.execution, result.permitted.finding, result.permitted.fix) == expected
    assert required <= codes(result)
    assert len(result.runs) == len(baseline) + len(candidate)


def test_same_evidence_same_result():
    evidence = AssessmentEvidence(plan=PLAN, baseline=(REPRO, run(witness=None)), candidate=(SAFE,))
    assert assess(evidence) == assess(AssessmentEvidence.model_validate_json(evidence.model_dump_json()))


def permitted(execution='completed', finding='reproduced', fix='verified'):
    baseline = {'reproduced': (REPRO,), 'not_reproduced': (SAFE,), 'inconclusive': (run(witness=None),)}[finding]
    candidate = {'verified': (SAFE,), 'not_verified': (run('passed', witness=None),), 'not_applicable': ()}[fix]
    result = assess(AssessmentEvidence(plan=PLAN, baseline=baseline, candidate=candidate))
    assert result.permitted == Disposition(execution=execution, finding=finding, fix=fix)
    return result


@pytest.mark.parametrize('proposal,gate,admitted', [
    (('completed', 'reproduced', 'verified'), ('completed', 'reproduced', 'verified'), True),
    (('completed', 'reproduced', 'not_verified'), ('completed', 'reproduced', 'verified'), True),
    (('completed', 'inconclusive', 'not_verified'), ('completed', 'reproduced', 'verified'), True),
    (('completed', 'inconclusive', 'verified'), ('completed', 'reproduced', 'verified'), False),
    (('completed', 'reproduced', 'verified'), ('completed', 'reproduced', 'not_verified'), False),
    (('completed', 'reproduced', 'not_verified'), ('completed', 'inconclusive', 'not_verified'), False),
    (('completed', 'not_reproduced', 'not_verified'), ('completed', 'reproduced', 'verified'), False),
    (('completed', 'refuted_in_scope', 'not_verified'), ('completed', 'not_reproduced', 'not_verified'), False),
    (('completed', 'not_reproduced', 'not_verified'), ('completed', 'not_reproduced', 'not_verified'), True),
    (('blocked', 'reproduced', 'verified'), ('completed', 'reproduced', 'verified'), False),
    (('completed', 'reproduced', 'not_verified'), ('completed', 'reproduced', 'not_applicable'), False),
    (('completed', 'reproduced', 'not_applicable'), ('completed', 'reproduced', 'verified'), False),
    (('completed', 'reproduced', 'not_applicable'), ('completed', 'reproduced', 'not_applicable'), True),
])
def test_admission_refuses_proposals_stronger_than_evidence(proposal, gate, admitted):
    result = permitted(*gate)
    proposed = Disposition(execution=proposal[0], finding=proposal[1], fix=proposal[2])
    admission = admit(proposed, result)
    assert admission.admitted is admitted
    assert admission.disposition == (proposed if admitted else result.permitted)
    assert bool(admission.rejections) is not admitted


@pytest.mark.parametrize('build', [
    lambda: AssessmentEvidence(plan=PLAN, baseline=()),
    lambda: ObservationPlan.model_validate(PLAN.model_dump() | {'security_test_id': CONTROL}),
    lambda: ObservedOutcome(test_id=CONTROL, outcome='passed', failure=PLANNED_FAILURE),
    lambda: RunEvidence.model_validate(REPRO.model_dump() | {'verdict': 'reproduced'}),
    lambda: ExpectedFailure(exception_type='AssertionError', path=TESTS, function='f', assertion_lines=()),
    lambda: Witness(artifact_sha256='not-a-digest', path_reached=True, effect='observed'),
])
def test_contracts_refuse_ambiguous_or_extra_inputs(build):
    with pytest.raises(ValidationError):
        build()
