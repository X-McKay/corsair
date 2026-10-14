"""Matched drafting-only pilot: one pair call versus control then exploit; no code execution."""
import argparse
import asyncio
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter

from pydantic import TypeAdapter
from pydantic_ai import capture_run_messages, models
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RunUsage, UsageLimits

from corsair.inference.config import load_agent_config
from corsair.inference.models import configured_model
from corsair.ports.test_runner import ApprovedPatch, PatchFile
from evals.issue_analysis.evaluate import describe_model
from .cases import ROOT, load_cases, scripted_patches


@dataclass(frozen=True)
class Budget:
    request_limit: int = 10
    tool_calls_limit: int = 9
    total_tokens_limit: int = 128000
    task_seconds: float = 900
    output_retries: int = 1


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def patch_for(files, inputs):
    return ApprovedPatch(tuple(PatchFile(f.path, f.content.encode()) for f in files),
                         tuple(inputs.environment.approved_test_paths))


def scripted_model(inputs):
    """Fixed SDK plumbing only; never used when an explicit live model is supplied."""
    patches = scripted_patches()
    step = 0
    def respond(messages, info):
        nonlocal step
        step += 1
        if step == 1:
            return ModelResponse(parts=[ToolCallPart('read_source', {'path': source.path, 'start_line': 1}) for source in (*inputs.source_files, *inputs.frozen_control)])
        if step == 2:
            paths = [inputs.control_test_path, inputs.exploit_test_path] if inputs.role == 'pair' else [
                inputs.control_test_path if inputs.role == 'control' else inputs.exploit_test_path]
            return ModelResponse(parts=[ToolCallPart('write_test_file', {'path': path, 'content': patches[path]}) for path in paths])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
            {'draft': {'status': 'drafted', 'limitations': ['Draft only; independent validity review and native execution remain required.']}})])
    return FunctionModel(respond)


async def run_arm(base, arm, *, model=None, budget=Budget(), model_factory=None, guidance="tailored"):
    from .agent import create_drafting_agent
    from .contracts import DraftingInput, DraftOutput, Drafted, Blocked
    from .dependencies import DraftingDependencies
    from .prompts import drafting_prompt, INSTRUCTIONS, SKILL_SHA256, role_skills
    from .tools import TOOLSET_SHA256
    if arm not in ('pair', 'split'):
        raise ValueError('variant must be pair or split')
    usage = RunUsage()
    started = perf_counter()
    stages, frozen_control, final = [], (), None
    scripted = model is None
    for role in (('pair',) if arm == 'pair' else ('control', 'exploit')):
        stage_input = dict(base, role=role, frozen_control=[f.model_dump(mode='json') for f in frozen_control])
        try:
            inputs = DraftingInput.model_validate(stage_input)
        except ValueError as exc:
            # An admitted draft need not fit the next role's bounded read inventory.
            # Keep the first stage and classify this before any second model call.
            current_usage = TypeAdapter(RunUsage).dump_python(usage, mode='json')
            stages.append({'role': role, 'input': stage_input, 'input_sha256': digest(stage_input),
                'prompt': None, 'messages': [], 'output': None,
                'usage_before': current_usage, 'usage_cumulative': current_usage,
                'failure': {'type': type(exc).__name__, 'detail': str(exc),
                    'classification': 'handoff_admission' if frozen_control else 'input_admission'}})
            break
        selected = model if model is not None else (model_factory or scripted_model)(inputs)
        deps = DraftingDependencies(inputs)
        agent = create_drafting_agent(selected, role=role, output_retries=budget.output_retries, guidance=guidance)
        messages, result, failure = [], None, None
        before = TypeAdapter(RunUsage).dump_python(usage, mode='json')
        stage_started = perf_counter()
        prompt = drafting_prompt(inputs)
        try:
            remaining = budget.task_seconds - (perf_counter() - started)
            if remaining <= 0:
                raise TimeoutError('shared drafting deadline exhausted before next stage')
            with capture_run_messages() as messages, models.override_allow_model_requests(not scripted):
                result = await asyncio.wait_for(agent.run(prompt, deps=deps, usage=usage,
                    usage_limits=UsageLimits(request_limit=budget.request_limit,
                        tool_calls_limit=budget.tool_calls_limit, total_tokens_limit=budget.total_tokens_limit)), remaining)
        except Exception as exc:
            failure = {'type': type(exc).__name__, 'detail': str(exc)}
        after = TypeAdapter(RunUsage).dump_python(usage, mode='json')
        responses = [message for message in messages if isinstance(message, ModelResponse)]
        stages.append({'role': role, 'input': inputs.model_dump(mode='json'),
            'input_sha256': digest(inputs.model_dump(mode='json')), 'prompt': prompt,
            'instructions_sha256': sha256(INSTRUCTIONS.encode()).hexdigest(),
            'skill_sha256': SKILL_SHA256,
            'role_skills': role_skills(role, guidance),
            'role_skill_sha256': {key: sha256(text.encode()).hexdigest() for key, text in role_skills(role, guidance).items()}, 'toolset_sha256': TOOLSET_SHA256,
            'draft_schema_sha256': digest(TypeAdapter(DraftOutput).json_schema()),
            'output_schema_sha256': digest(TypeAdapter(Drafted | Blocked).json_schema()),
            'prompt_sha256': sha256(prompt.encode()).hexdigest(),
            'source_sha256': digest([f.model_dump(mode='json') for f in inputs.source_files]),
            'usage_before': before, 'usage_cumulative': after,
            'usage_source': 'scripted_estimate' if scripted else 'native_responses_partial_on_failure',
            'elapsed_seconds': perf_counter() - stage_started,
            'provider_usage_present': None if scripted else bool(responses) and all(r.usage.has_values() for r in responses),
            'messages': TypeAdapter(list[ModelMessage]).dump_python(messages, mode='json'),
            'output': result.output.model_dump(mode='json') if result else None, 'failure': failure})
        if result is None or result.output.status != 'drafted':
            break
        final = result.output
        if role == 'control':
            frozen_control = tuple(final.files)
            final = None
    complete = final is not None and len(stages) == (1 if arm == 'pair' else 2)
    files = (frozen_control + tuple(final.files)) if complete else ()
    patch = patch_for(files, inputs) if complete else None
    return {'arm': arm, 'base_input_sha256': digest(base), 'stages': stages,
        'draft_completed': complete, 'output': final.model_dump(mode='json') if final else None,
        'patch_sha256': patch.sha256 if patch else None,
        'files': [file.model_dump(mode='json') for file in files],
        'usage': TypeAdapter(RunUsage).dump_python(usage, mode='json'),
        'elapsed_seconds': perf_counter() - started, 'valid_pair': None,
        'failure_classification': next((stage['failure'].get('classification') for stage in stages if stage['failure']), None),
        'qualification': 'Drafting only; independent validity review and both native outcomes pending.'}


async def evaluate(evidence: Path, *, model=None, provider=None, repeat=1, budget=Budget(), arm='both', guidance='tailored'):
    from . import agent
    from .contracts import DraftingInput
    if arm not in ('pair', 'split', 'both'):
        raise ValueError('variant must be pair, split or both')
    case_version = 2 if guidance == "tailored" else 1
    cases = load_cases(case_version)
    evidence.mkdir(parents=True, exist_ok=False)
    configuration = {'version': 'split-authoring-experiment-v2', 'mode': 'scripted_fixture' if model is None else 'direct_local_provider',
        'model': describe_model(model) if model is not None else 'native FunctionModel scripted fixture',
        'provider': provider, 'budget': asdict(budget), 'repeat': repeat,
        'guidance': guidance, 'case_version': case_version,
        'manifest': json.loads((ROOT / f'manifest-v{case_version}.json').read_text()),
        'order': 'alternate across repetitions',
        'factory_sha256': sha256(Path(agent.__file__).read_bytes()).hexdigest(),
        'input_schema_sha256': digest(DraftingInput.model_json_schema()),
        'runner_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
        'primary_metric': 'valid pairs after independent review and native execution (pending)',
        'execution': 'none; drafting-only', 'task_retries': 0, 'max_concurrency': 1}
    (evidence / 'configuration.json').write_text(json.dumps(configuration, indent=2))
    attempts = []
    for case_index, case in enumerate(cases):
        for repetition in range(repeat):
            for selected_arm in ((('pair', 'split') if (case_index + repetition) % 2 == 0 else ('split', 'pair')) if arm == 'both' else (arm,)):
                receipt = await run_arm(case['inputs'], selected_arm, model=model, budget=budget, guidance=guidance)
                receipt.update(case=case['name'], repetition=repetition)
                attempt_dir = evidence / case['name'] / str(repetition) / selected_arm
                attempt_dir.mkdir(parents=True)
                filename = str((attempt_dir / 'receipt.json').relative_to(evidence))
                (attempt_dir / 'receipt.json').write_text(json.dumps(receipt, indent=2))
                (attempt_dir / 'output.json').write_text(json.dumps({key: receipt[key] for key in
                    ('case', 'arm', 'base_input_sha256', 'draft_completed', 'files', 'patch_sha256', 'qualification')}, indent=2))
                attempts.append({key: receipt[key] for key in ('case', 'repetition', 'arm', 'draft_completed', 'valid_pair', 'usage', 'elapsed_seconds', 'failure_classification') } | {'receipt': filename, 'output': str((attempt_dir / 'output.json').relative_to(evidence))})
    report = {'attempts': attempts, 'valid_pairs': None, 'draft_completed': sum(a['draft_completed'] for a in attempts),
              'qualification': 'Structural drafting result only; no semantic or execution qualification.'}
    (evidence / 'report.json').write_text(json.dumps(report, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--provider-config', type=Path)
    parser.add_argument('--guidance', choices=('legacy', 'tailored'), default='tailored')
    parser.add_argument('--repeat', type=int, choices=range(1, 4), default=1)
    parser.add_argument('--variant', '--arm', dest='arm', choices=('pair', 'split', 'both'), default='both')
    args = parser.parse_args()
    async def run():
        if args.provider_config is None:
            return await evaluate(args.evidence, repeat=args.repeat, arm=args.arm, guidance=args.guidance)
        config = load_agent_config(args.provider_config, 'authoring')
        async with configured_model(config) as model:
            return await evaluate(args.evidence, model=model, provider=config.model_dump(mode='json', exclude={'api_key_env'}), repeat=args.repeat, arm=args.arm, guidance=args.guidance)
    report = asyncio.run(run())
    print(json.dumps(report, indent=2))
    return 0 if all(a['draft_completed'] for a in report['attempts']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
