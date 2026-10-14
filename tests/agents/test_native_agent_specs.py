"""Native construction preserves frozen instructions, tools, contracts and dependencies."""
import json
from pathlib import Path
import pytest
from tests.agents.manifest_capture import capture, capture_root

BEFORE = Path(__file__).parent / 'fixtures/native_manifest_before.json'


@pytest.mark.parametrize('role', ['control_authoring', 'exploit_authoring', 'planning', 'assessment',
                                   'environment', 'identification', 'repository_identification'])
def test_native_skills_progressively_disclose_bodies_preserving_domain_tools(role):
    from importlib import import_module
    package={'planning':'test_planning','assessment':'evidence_assessment',
             'identification':'issue_identification','repository_identification':'issue_identification'}.get(role,role)
    prompts=import_module('corsair.agents.'+package+'.prompts')
    skill_id=prompts.REPOSITORY_SKILL_ID if role=='repository_identification' else prompts.SKILL_ID
    skill_file=Path(prompts.__file__).parent/'skills'/skill_id/'SKILL.md'
    body=skill_file.read_text().split('---',2)[2].strip()
    current=(capture(role,activate=True) if role in ('control_authoring','exploit_authoring','planning','assessment')
             else capture_root(role,activate=True))
    initial=current['initial_offer']
    loaded=current.get('native_offer',current)
    assert body not in initial['instructions']
    assert any(body in instructions for instructions in current['loaded_instructions'])
    assert skill_id in initial['instructions']
    names={tool['name'] for tool in initial['function_tools']}
    assert 'load_capability' in names
    assert not names.intersection({'read_file','write_file','edit_file','run_command','shell','execute'})
    history=json.loads((BEFORE if role in ('control_authoring','exploit_authoring','planning','assessment')
                       else BEFORE.parent/'native_manifest_root_before.json').read_text())[role]
    historical=history.get('native_offer',history)
    assert names-{'load_capability'} == {tool['name'] for tool in historical['function_tools']}
    assert loaded['output_tools'] == historical['output_tools']
    if role in ('control_authoring','exploit_authoring'):
        common=Path(prompts.__file__).parents[1]/'probe_authoring/skills/native-probe-boundary/SKILL.md'
        common_body=common.read_text().split('---',2)[2].strip()
        assert common_body not in initial['instructions']
        assert any(common_body in instructions for instructions in current['loaded_instructions'])


@pytest.mark.parametrize('package', ['control_authoring', 'exploit_authoring', 'environment',
                                   'issue_identification', 'test_planning', 'evidence_assessment'])
def test_package_manifest_keeps_operator_policy_and_tool_authority_in_python(package):
    from pydantic_ai.agent.spec import AgentSpec
    root = Path(__file__).parents[2] / 'src/corsair/agents' / package
    for path in root.glob('*agent.yaml'):
        native = AgentSpec.from_file(path)
        assert native.model is None and native.model_settings is None
        assert not native.capabilities
        assert native.output_schema is None and native.deps_schema is None
        assert set(native.metadata) == {'config_version', 'prompt_version'}
