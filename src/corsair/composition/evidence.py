"""Deterministic handoffs into the SPEC-0027 gates: plan and patch to expectations, native runs to evidence.

Trusted code only: nothing here reads model text beyond the typed plan and patch fields, and
nothing invents an observation. A run carries a witness only when the execution node's probe
record for that run is admitted (SPEC-0033); otherwise ``witness=None``.
"""

from hashlib import sha256
import json
import re

from corsair.agents.evidence_assessment.contracts import MAX_ITEM_CHARS, EvidenceAssessment, EvidenceItem
from corsair.agents.issue_identification.contracts import IssueIdentification
from corsair.agents.test_authoring.contracts import TestPatch
from corsair.agents.source.contracts import SourceFile
from corsair.agents.test_planning.contracts import PlannedWitness, ReadyTestPlan, WitnessFacility
from corsair.core.disposition import (ClassifiedFailure, EnvironmentIdentity, ExpectedFailure, ObservationPlan,
                                      ObservedOutcome, Revision, RunEvidence, SandboxEvent, Witness)
from corsair.ports.execution import ExecutionReceipt
from corsair.ports.test_runner import ApprovedPatch, NativeTestRun, PatchFile, TestCaseResult, WitnessRequest, native_test_function

TOKEN = re.compile(r'^[A-Za-z0-9_.:-]{1,128}$')


def observation_plan(plan: ReadyTestPlan, patch: TestPatch) -> ObservationPlan:
    """The agreed mapping; the patch must realize exactly this plan's two tests."""
    if (patch.control_test_id, patch.security_test_id) != (plan.control.test_id, plan.security.test_id):
        raise ValueError('patch test ids differ from the plan')
    if patch.discovery_command != plan.discovery_command:
        raise ValueError('patch discovery command differs from the plan')
    if plan.security.test_path not in {item.path for item in patch.files}:
        raise ValueError('patch does not contain the planned security test file')
    return ObservationPlan(
        control_test_id=plan.control.test_id, security_test_id=plan.security.test_id,
        expected_failure=ExpectedFailure(exception_type=plan.security_expectation.failure_type,
                                         path=plan.security.test_path,
                                         function=native_test_function(plan.security.test_id),
                                         assertion_lines=patch.security_assertion_lines),
        expected_safe_behavior=plan.security_expectation.safe_behavior,
        frozen_patch_sha256=patch.patch_sha256,
        observation_mode="unit_test" if plan.security.observation is not None else "effect_witness",
        test_plan_sha256=sha256(plan.model_dump_json().encode()).hexdigest())


# The effects the operator probe records (SPEC-0033); a recorder of any other kind cannot bind a request yet.
PROBE_EFFECTS = frozenset({"file_open"})


def witness_request(identification: IssueIdentification, envelope: WitnessRequest | None,
                    planned: PlannedWitness | None, recorders: tuple[WitnessFacility, ...] = ()) -> WitnessRequest:
    """The operator's approved envelope, used only when the admitted identification names exactly its target
    and the plan's security witness is the effect that envelope records.

    Without an envelope, `recorders` (the operator's witness facilities for the selected framework, SPEC-0073)
    bind the request instead: the admitted identification's target and the plan's subject, accepted only when the
    planned facility is one of them, its effect is that recorder's kind and one the probe records, and the subject
    is a plain file name. Nothing per case is approved; the rules are the framework table's.

    Until SPEC-0040 binds the plan's subject at execution, a planned effect the probe does not record, or a
    subject other than the envelope's file, is refused here so its gates stay inconclusive.
    """
    if planned is None:
        raise ValueError('unit test plan does not request instrumentation')
    if identification.status != 'ready' or identification.target is None:
        raise ValueError('a witness needs a ready identification target')
    target = identification.target
    if envelope is None:
        if not recorders:
            raise ValueError('the operator approved no witness envelope for this case')
        recorder = next((r for r in recorders if r.id == planned.facility), None)
        if recorder is None or recorder.kind != planned.effect:
            raise ValueError(f'the planned {planned.effect} witness names no operator recorder of that kind')
        if planned.effect not in PROBE_EFFECTS:
            raise ValueError(f'the planned {planned.effect} witness is not recorded by the operator probe')
        # The probe matches a plain file name; a directory-prefixed subject names another path.
        if '/' in planned.subject:
            raise ValueError('the planned witness subject is not a plain file name the probe matches')
        return WitnessRequest(target.source.path, target.symbol, planned.subject)
    if (target.source.path, target.symbol) != (envelope.target_path, envelope.target_symbol):
        raise ValueError('the identified target is outside the operator witness envelope')
    if planned.effect != 'file_open':
        raise ValueError(f'the planned {planned.effect} witness is not recorded by the operator probe')
    # The probe matches a plain file name, so only that exact subject is represented; a directory-prefixed
    # subject names another path and is refused until execution binds the whole subject.
    if planned.subject != envelope.effect_name:
        raise ValueError('the planned witness subject is not the operator witness envelope effect')
    return envelope


def freeze(patch: TestPatch, approved_paths: tuple[str, ...]) -> ApprovedPatch:
    """The exact bytes every revision executes; refused if they no longer hash to the authored digest."""
    frozen = ApprovedPatch(tuple(PatchFile(item.path, item.content.encode()) for item in patch.files), approved_paths)
    if frozen.sha256 != patch.patch_sha256:
        raise ValueError('frozen patch bytes differ from the authored patch digest')
    return frozen


def _token(value: str | None) -> str | None:
    return value if value is not None and TOKEN.fullmatch(value) else None


def _outcome(case: TestCaseResult) -> ObservedOutcome:
    failure = None
    if case.outcome == 'failed' and case.failure is not None:
        detail = case.failure
        # Anything the gate's types cannot hold is unclassified, never coerced into a match.
        failure = ClassifiedFailure(
            exception_type=_token(detail.type),
            path=detail.path if detail.path is not None and len(detail.path) <= 256 else None,
            function=_token(detail.function), line=detail.line)
    return ObservedOutcome(test_id=case.test_id, outcome=case.outcome, failure=failure)


def _receipt(observed: NativeTestRun) -> ExecutionReceipt | None:
    execution, discovery = observed.execution, observed.discovery
    if execution is not None and execution.receipt is not None:
        return execution.receipt
    return discovery.receipt if discovery is not None else None


def run_evidence(observed: NativeTestRun, *, environment: EnvironmentIdentity, witness: Witness | None = None,
                 sandbox_events: tuple[SandboxEvent, ...] | None = None) -> RunEvidence:
    """One fresh native run as gate input. Delivery and completion come from the last receipt.

    The gate reads an empty event tuple as observed absence, so a witness is admitted only together with
    sandbox events the execution node actually observed; unobserved events stay None and no witness is used.
    """
    if witness is not None and sandbox_events is None:
        raise ValueError('a witness needs the sandbox events observed for the same run')
    receipt = _receipt(observed)
    layer = observed.failure_layer
    if receipt is None:
        # Nothing was dispatched (workspace refusal) or no receipt survived: never assume completion.
        delivery, completion = ('not_dispatched' if layer == 'workspace' else 'unknown'), 'unknown'
    else:
        delivery, completion = receipt.delivery, receipt.completion
    failure = None
    if layer == 'discovery' and observed.discovery is not None and observed.discovery.status == 'collection_error':
        failure = 'discovery'
    elif layer is not None:
        failure = 'timeout' if receipt is not None and 'timeout' in receipt.reason else 'unknown'
    execution = observed.execution
    cases = execution.cases if execution is not None and execution.status == 'completed' else ()
    return RunEvidence(
        delivery=delivery, completion=completion, execution_failure=failure, patch_sha256=observed.patch_sha256,
        discovered_test_ids=observed.discovery.test_ids if observed.discovery is not None else (),
        outcomes=tuple(_outcome(case) for case in cases), witness=witness, environment=environment,
        sandbox_events=sandbox_events or (),
        source_sha256=observed.workspace.source.sha256 if observed.workspace is not None else None)


def _item(item_id: str, kind: str, content: str, revision: Revision | None = None,
          run: int | None = None, source_sha256: str | None = None, path: str | None = None) -> EvidenceItem:
    complete = len(content) <= MAX_ITEM_CHARS
    if not complete:
        marker = f'\n[truncated by trusted code from {len(content)} characters]'
        content = content[:MAX_ITEM_CHARS - len(marker)] + marker
    content = content or '(empty)'
    return EvidenceItem(item_id=item_id, kind=kind, revision=revision, run=run,
                        sha256=sha256(content.encode('utf-8')).hexdigest(), content=content,
                        source_sha256=source_sha256, complete=complete, path=path)


def _receipt_summary(observed: NativeTestRun) -> str:
    receipt = _receipt(observed)
    summary = {'operation': observed.operation, 'patch_sha256': observed.patch_sha256,
               'failure_layer': observed.failure_layer, 'detail': observed.detail[:2048], 'cleanup': observed.cleanup,
               'discovery_status': observed.discovery.status if observed.discovery else None,
               'discovered_test_ids': list(observed.discovery.test_ids) if observed.discovery else [],
               'execution_status': observed.execution.status if observed.execution else None}
    if receipt is not None:
        summary |= {'delivery': receipt.delivery, 'completion': receipt.completion, 'reason': receipt.reason,
                    'native_exit': receipt.native_exit, 'elapsed_seconds': round(receipt.elapsed_seconds, 3)}
    return json.dumps(summary, indent=2, sort_keys=True)


def review_items(plan: ObservationPlan, patch: TestPatch,
                 review_sources: dict[Revision, tuple[SourceFile, ...]],
                 source_identities: dict[Revision, str],
                 test_plan: ReadyTestPlan, issue: str) -> tuple[EvidenceItem, ...]:
    """Outcome-blind frozen artifacts, captured before either native probe executes.

    Paths are metadata, so an admitted source file's full content still fits the evidence
    bound. Source stays whole and available for selective numbered reads; this function
    neither chooses a language-specific symbol boundary nor silently drops helpers.
    """
    items = [_item('plan', 'plan', plan.model_dump_json(indent=2)),
             _item('test-plan', 'plan', test_plan.model_dump_json(indent=2)),
             _item('reported-condition', 'plan', issue)]
    for revision, sources in review_sources.items():
        if revision not in source_identities:
            continue
        for index, source in enumerate(sources):
            items.append(_item(f'{revision}-source-{index}', 'source', source.content,
                               revision, 0, source_sha256=source_identities[revision], path=source.path))
    items.extend(_item(f'patch-{index}', 'patch', item.content, path=item.path)
                 for index, item in enumerate(patch.files))
    return tuple(items)


def evidence_items(plan: ObservationPlan, patch: TestPatch, environment: EnvironmentIdentity,
                   runs: dict[Revision, tuple[NativeTestRun, ...]],
                   admitted: frozenset[Revision] | set[Revision] = frozenset(),
                   review_sources: dict[Revision, tuple[SourceFile, ...]] | None = None,
                   test_plan: ReadyTestPlan | None = None, issue: str | None = None,
                   frozen_review: EvidenceAssessment | None = None) -> tuple[EvidenceItem, ...]:
    """Frozen artifacts the assessment agent may read; revisions are named baseline and candidate only."""
    items = [_item('plan', 'plan', plan.model_dump_json(indent=2)),
             _item('environment', 'environment', environment.model_dump_json(indent=2))]
    if frozen_review is not None:
        items.append(_item('test-validity', 'test_validity', frozen_review.model_dump_json(indent=2)))
    if review_sources is not None:
        if test_plan is not None:
            items.append(_item('test-plan', 'plan', test_plan.model_dump_json(indent=2)))
        if issue is not None:
            items.append(_item('reported-condition', 'plan', issue))
        for revision, sources in review_sources.items():
            if revision not in runs:
                continue
            for index, source in enumerate(sources):
                items.append(_item(f'{revision}-source-{index}', 'source',
                                   source.content, revision, 0,
                                   source_sha256=(runs[revision][0].workspace.source.sha256
                                                  if runs[revision][0].workspace is not None else None),
                                   path=source.path))
    items += [_item(f'patch-{index}', 'patch',
                    item.content, path=item.path if review_sources is not None else None)
              for index, item in enumerate(patch.files)]
    for revision, observed_runs in runs.items():
        for index, observed in enumerate(observed_runs):
            prefix = f'{revision}-{index}'
            items.append(_item(f'{prefix}-receipt', 'receipt', _receipt_summary(observed), revision, index))
            execution = observed.execution
            if execution is not None and execution.receipt is not None and execution.receipt.stdout:
                # The runner's wrapper prints exactly the native JUnit file on stdout.
                items.append(_item(f'{prefix}-junit', 'junit',
                                   execution.receipt.stdout.decode('utf-8', 'replace'), revision, index))
            elif observed.discovery is not None and observed.discovery.errors:
                items.append(_item(f'{prefix}-stdout', 'stdout', observed.discovery.errors, revision, index))
            captured = observed.witness
            if captured is not None and captured.status == 'captured' and revision in admitted:
                # Only an admitted probe record, never test output or a refused record; the gate decides its weight.
                record = json.dumps(json.loads(captured.record), indent=2, sort_keys=True)
                items.append(_item(f'{prefix}-witness', 'witness', record, revision, index))
    return tuple(items)
