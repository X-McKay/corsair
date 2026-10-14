"""Native construction preserves frozen instructions, tools, contracts and dependencies."""
import json
from pathlib import Path
import pytest
from tests.agents.manifest_capture import capture, capture_root

BEFORE = Path(__file__).parent / 'fixtures/native_manifest_before.json'


@pytest.mark.parametrize('role', ['control_authoring', 'exploit_authoring', 'planning', 'assessment'])
def test_native_manifest_complete_offer_is_byte_equal_to_frozen_factory(role):
    assert capture(role) == json.loads(BEFORE.read_text())[role]


@pytest.mark.parametrize('role', ['environment', 'identification', 'repository_identification'])
def test_root_native_manifest_offers_preserve_frozen_pre_migration_construction(role):
    before = json.loads((BEFORE.parent / 'native_manifest_root_before.json').read_text())
    assert capture_root(role) == before[role]


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
