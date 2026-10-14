"""Native offer parity and package authority before any model/tool execution."""
import asyncio
import json
from pathlib import Path
import pytest
import yaml
from pydantic import ValidationError
from pydantic_ai import models
from pydantic_ai.capabilities import Capability
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.agent.spec import AgentSpec
from corsair.agents import spec
from tests.agents.manifest_capture import capture

BEFORE=Path(__file__).parent/'fixtures/native_manifest_before.json'

@pytest.mark.parametrize('role',['control_authoring','exploit_authoring','planning','assessment'])
def test_native_manifest_complete_offer_is_byte_equal_to_frozen_factory(role):
    expected=json.loads(BEFORE.read_text())[role]
    assert capture(role)==expected
    loaded=spec.load_agent_spec(role)
    assert len(loaded.spec_sha256)==64 and len(loaded.selection_sha256)==64


def write_manifest(tmp_path,monkeypatch, *, selection=('allowed',), **fields):
    data={'name':'manifest-test','description':'Capture native selection only','instructions':'Literal instructions',
          'metadata':{'config_version':'test-config-v1','prompt_version':'test-prompt-v1','capability_selection':list(selection)}}
    data.update(fields)
    path=tmp_path/'agent.yaml';path.write_text(yaml.safe_dump(data))
    monkeypatch.setitem(spec._PATHS,'control_authoring',path)
    return path


@pytest.mark.parametrize('field,value',[('model','provider:untrusted'),('model_settings',{'max_tokens':99999}),
    ('capabilities',[{'import':'os.system'}]),('retries',100),('output_schema',{'type':'string'}),
    ('deps_schema',{}),('unknown',True)])
def test_package_rejects_forbidden_native_fields_before_native_loading(tmp_path,monkeypatch,field,value):
    write_manifest(tmp_path,monkeypatch,**{field:value})
    def forbidden(*a,**k):raise AssertionError('native loader must not see a forbidden envelope')
    monkeypatch.setattr(AgentSpec,'from_file',forbidden)
    with pytest.raises(ValidationError):spec.load_agent_spec('control_authoring')


def test_manifest_selection_actually_selects_registered_native_capability(tmp_path,monkeypatch):
    write_manifest(tmp_path,monkeypatch,selection=('selected',))
    loaded=spec.load_agent_spec('control_authoring');calls=[];seen=[]
    def selected():
        calls.append('selected')
        return Capability(id='selected',instructions='Selected native procedure')
    def excluded():
        raise AssertionError('unselected capability must never be assembled')
    def respond(messages,info):
        seen.append(info.instructions)
        return ModelResponse(parts=[TextPart('done')])
    agent=spec.build_agent(loaded,model=FunctionModel(respond),deps_type=type(None),output_type=str,
        capability_registry={'selected':selected,'excluded':excluded},output_retries=0)
    async def run():
        with models.override_allow_model_requests(False):return await agent.run('request')
    assert asyncio.run(run()).output=='done'
    assert calls==['selected'] and 'Selected native procedure' in seen[0]


def test_unknown_selector_is_rejected_before_any_builder(tmp_path,monkeypatch):
    write_manifest(tmp_path,monkeypatch,selection=('allowed','arbitrary-import'))
    loaded=spec.load_agent_spec('control_authoring')
    def forbidden():raise AssertionError('no capability may be built before all selectors validate')
    with pytest.raises(ValueError,match='unknown admitted capability'):
        spec.build_agent(loaded,model=FunctionModel(lambda m,i:None),deps_type=type(None),output_type=str,
            capability_registry={'allowed':forbidden},output_retries=0)


def test_only_fixed_role_paths_and_explicit_native_model_are_admitted(tmp_path,monkeypatch):
    with pytest.raises(ValueError,match='unknown trusted agent role'):spec.load_agent_spec(str(tmp_path/'agent.yaml'))
    path=write_manifest(tmp_path,monkeypatch)
    loaded=spec.load_agent_spec('control_authoring')
    with pytest.raises(TypeError,match='explicit native Model'):
        spec.build_agent(loaded,model='provider:implicit',deps_type=type(None),output_type=str,
            capability_registry={'allowed':lambda:Capability(id='allowed')},output_retries=0)
    with pytest.raises(TypeError,match='TemporalDurability'):
        spec.build_agent(loaded,model=FunctionModel(lambda m,i:None),deps_type=type(None),output_type=str,
            capability_registry={'allowed':lambda:Capability(id='allowed')},output_retries=0,extra_capabilities=[Capability(id='arbitrary')])
    path.unlink();path.symlink_to(tmp_path/'other.yaml')
    with pytest.raises(ValueError,match='not symlinks'):spec.load_agent_spec('control_authoring')


def test_mutated_native_authority_is_rejected_again_before_assembly(tmp_path,monkeypatch):
    write_manifest(tmp_path,monkeypatch)
    loaded=spec.load_agent_spec('control_authoring')
    loaded.spec.model='provider:implicit'
    with pytest.raises(ValidationError):
        spec.build_agent(loaded,model=FunctionModel(lambda m,i:None),deps_type=type(None),output_type=str,
            capability_registry={'allowed':lambda:Capability(id='allowed')},output_retries=0)


def test_inplace_mutation_of_native_default_capability_list_is_refused(tmp_path,monkeypatch):
    write_manifest(tmp_path,monkeypatch)
    loaded=spec.load_agent_spec('control_authoring')
    loaded.spec.capabilities.append({'import':'untrusted.capability'})
    with pytest.raises(ValueError,match='native capability definitions'):
        spec.build_agent(loaded,model=FunctionModel(lambda m,i:None),deps_type=type(None),output_type=str,
            capability_registry={'allowed':lambda:Capability(id='allowed')},output_retries=0)


@pytest.mark.parametrize('role',['environment','identification','repository_identification'])
def test_root_native_manifest_offers_preserve_frozen_pre_migration_construction(role):
    from tests.agents.manifest_capture import capture_root
    before=json.loads((BEFORE.parent/'native_manifest_root_before.json').read_text())
    assert capture_root(role)==before[role]


@pytest.mark.parametrize('field', ['instructions', 'name', 'description'])
def test_mutated_literal_native_envelope_cannot_keep_original_identity(tmp_path,monkeypatch,field):
    write_manifest(tmp_path,monkeypatch)
    loaded=spec.load_agent_spec('control_authoring')
    identity=dict(loaded.identity)
    setattr(loaded.spec,field,'Changed literal envelope')
    def forbidden():raise AssertionError('mutated envelope must be refused before capability assembly')
    with pytest.raises(ValueError,match='original envelope'):
        spec.build_agent(loaded,model=FunctionModel(lambda m,i:None),deps_type=type(None),output_type=str,
            capability_registry={'allowed':forbidden},output_retries=0)
    assert loaded.identity==identity
