"""Frozen outcome-blind semantic review evaluation; scripted mode checks plumbing, live mode judges skill behavior."""
import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from pydantic import TypeAdapter
from pydantic_ai import capture_run_messages, models
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, ToolReturnPart
from evals.native_skills import load_skills
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RunUsage
from pydantic_evals import Case, Dataset, set_eval_attribute
from pydantic_evals.evaluators import Evaluator

from corsair.agents.evidence_assessment import (MANIFEST_IDENTITY, CONFIG_VERSION, PROMPT_VERSION, SKILL_SHA256,
    TOOLSET_SHA256, assessment_prompt, create_evidence_assessment_agent)
from corsair.agents.evidence_assessment.contracts import ValidityInput
from corsair.agents.evidence_assessment.dependencies import AssessmentDependencies
from corsair.inference.config import load_agent_config
from corsair.inference.models import configured_model
from evals.cases import LANGUAGES, load_set, set_digest
from evals.evidence_assessment.evaluate import EvaluationBudget, describe_model, record_count

EVALUATOR_VERSION = 'unit-validity-v2-structured-classification'
SUITE = 'evidence_assessment'
# Pre-execution validity sets (per-case directories, evals/cases.py). Each oracle holds the expected flags and the
# structured review the scripted model replays. breadth_pending predates the structured review (no scripted_review).
SETS = ('unit', 'unit-transfer', 'breadth_pending')
FLAGS = ('source_linked', 'condition_exercised', 'assertions_relevant', 'dependency_scope_valid')


def dataset(cases='unit', language=None):
    return Dataset(name=f"unit-test-validity-{cases}", cases=[Case(name=c.name,
        inputs=ValidityInput.model_validate_json(json.dumps(c.input)), metadata=c.oracle)
        for c in load_set(SUITE, cases, language)])


def review_classification(output, expected):
    validity = output.bound_validity.get('baseline')
    if validity is None:
        return 'missing_review'
    approved = all(getattr(validity, flag) for flag in FLAGS)
    valid = all(expected.values())
    if approved:
        return 'correct_approval' if valid else 'dangerous_false_approval'
    if valid:
        return 'false_rejection'
    return ('correct_rejection' if all(getattr(validity, flag) == value for flag, value in expected.items())
            else 'rejection_wrong_reason')


def outcome_summary(report):
    from collections import Counter
    counts = Counter()
    for case in report.cases:
        if case.evaluator_failures:
            counts['evaluator_defect'] += 1
        else:
            label = case.labels.get('review_classification')
            counts[label.value if label else 'evaluator_defect'] += 1
    for failure in report.failures:
        detail = failure.error_message.lower()
        counts['contract_failure' if any(marker in detail for marker in
            ('validationerror', 'maximum output retries', 'output validation')) else 'task_failure'] += 1
    return {'evaluator_version': EVALUATOR_VERSION, 'attempts': len(report.cases) + len(report.failures),
        'outcomes': dict(counts), 'report_evaluator_defects': len(report.report_evaluator_failures)}




class ValidityScore(Evaluator):
    def evaluate(self, ctx):
        review = ctx.output.bound_validity.get('baseline')
        expected = ctx.metadata['expected']
        return {'semantic_validity': review is not None and all(
            getattr(review, flag) == expected[flag] for flag in expected),
            'outcome_blind_contract': ctx.output.evidence is None and ctx.output.gate_result is None,
            'bound_review': 'baseline' in ctx.output.bound_validity,
            'review_classification': review_classification(ctx.output, expected)}


def scripted_model(inputs, expected):
    async def respond(messages, info):
        activation = load_skills(messages, info, ['assess-evidence'])
        if activation is not None:
            return activation
        reads = [p.content for m in messages for p in m.parts if isinstance(p, ToolReturnPart)
                 and p.tool_name == 'read_evidence']
        for item in inputs.items:
            end = max((r.end_line for r in reads if r.item_id == item.item_id), default=0)
            if end < len(item.content.splitlines()):
                return ModelResponse(parts=[ToolCallPart('read_evidence',
                    {'item_id': item.item_id, 'start_line': end + 1})])
        citations = [{'item_id': i.item_id, 'start_line': 1,
            'end_line': min(80, len(i.content.splitlines()))} for i in inputs.items]
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            'execution': 'unknown', 'finding': 'inconclusive', 'fix': 'not_applicable',
            'application_observations': [], 'sandbox_observations': [],
            'interpretation': {'statement': 'Reviewed frozen inputs before execution', 'citations': citations[:1]},
            'limitations': ['Scripted oracle replay measures plumbing, not semantic judgment'],
            'validity_reviews': [expected['scripted_review']]})])
    return FunctionModel(respond)


async def evaluate(destination, repeat=1, model=None, cases='unit', language=None):
    destination.mkdir(parents=True, exist_ok=False)
    corpus = dataset(cases, language)
    corpus.evaluators.append(ValidityScore())
    offline = model is None
    budget = EvaluationBudget(repeat=repeat)
    selected = {c.inputs.model_dump_json(): scripted_model(c.inputs, c.metadata) for c in corpus.cases}
    metadata = {'mode': 'scripted_fixture' if offline else 'direct_local_provider',
        'model': describe_model(model or next(iter(selected.values()))),
        'prompt_version': PROMPT_VERSION, 'config_version': CONFIG_VERSION,
        'skill_sha256': SKILL_SHA256, 'toolset_sha256': TOOLSET_SHA256,
        'evaluator_version': EVALUATOR_VERSION, 'dataset': cases, 'language': language,
        'dataset_sha256': set_digest(SUITE, cases), 'budget': budget.model_dump(),
        'task_retries': 0, 'max_concurrency': 1}
    metadata |= MANIFEST_IDENTITY
    (destination / 'configuration.json').write_text(json.dumps(metadata, indent=2))

    async def task(inputs):
        usage, result, failure = RunUsage(), None, None
        started = perf_counter()
        with capture_run_messages() as messages:
            try:
                with models.override_allow_model_requests(not offline):
                    agent = create_evidence_assessment_agent(model or selected[inputs.model_dump_json()])
                    result = await asyncio.wait_for(agent.run(assessment_prompt(inputs),
                        deps=AssessmentDependencies(inputs), usage=usage,
                        usage_limits=budget.limits(inputs).usage_limits()), timeout=budget.task_seconds)
                return result.output
            except BaseException as exc:
                failure = {'type': type(exc).__name__, 'detail': str(exc)}
                raise
            finally:
                receipt = {'failure': failure, 'elapsed_seconds': perf_counter() - started,
                    'usage': TypeAdapter(RunUsage).dump_python(usage, mode='json'),
                    'messages': TypeAdapter(list[ModelMessage]).dump_python(messages, mode='json')}
                (destination / f'attempt-{uuid4()}.json').write_text(json.dumps(receipt, indent=2))
                set_eval_attribute('elapsed_seconds', receipt['elapsed_seconds'])
                for key in ('requests', 'tool_calls', 'input_tokens', 'output_tokens'):
                    record_count('observed_' + key, getattr(usage, key))
    report = await corpus.evaluate(task, repeat=repeat, max_concurrency=1, retry_task=None, progress=False)
    (destination / 'report.json').write_bytes(TypeAdapter(type(report)).dump_json(report, indent=2))
    (destination / 'outcomes.json').write_text(json.dumps(outcome_summary(report), indent=2))
    return not report.failures and not report.report_evaluator_failures and all(not c.evaluator_failures and all(a.value for a in c.assertions.values())
                                      for c in report.cases)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--repeat', type=int, default=1)
    parser.add_argument('--provider-config', type=Path)
    parser.add_argument('--cases', choices=SETS, default='unit')
    parser.add_argument('--language', choices=LANGUAGES, help="only this language's cases of the set")
    args = parser.parse_args()
    async def run():
        if args.provider_config is None:
            return await evaluate(args.evidence, args.repeat, cases=args.cases, language=args.language)
        config = load_agent_config(args.provider_config, 'assessment')
        async with configured_model(config) as model:
            return await evaluate(args.evidence, args.repeat, model, cases=args.cases, language=args.language)
    raise SystemExit(0 if asyncio.run(run()) else 1)

if __name__ == '__main__':
    main()
