"""Trusted YAML defaults and explicit operator overrides preserve budget/provider admission."""
import json
from pathlib import Path
import pytest
import yaml
from pydantic import ValidationError, model_validator
from corsair.policy.budget import (StageLimits, StageBudget, CompositionBudget, DEFAULT_BUDGET,
    BUDGET_POLICY_SHA256, load_budget, budget_sha256)
from corsair.inference.config import load_inference


def test_packaged_defaults_are_authoritative_and_direct_aliases_preserved():
    from hashlib import sha256
    from importlib.resources import files
    from corsair.composition import direct
    raw=files('corsair.policy').joinpath('budget.yaml').read_bytes()
    doc=yaml.safe_load(raw)
    assert BUDGET_POLICY_SHA256==sha256(raw).hexdigest()
    assert CompositionBudget().model_dump(mode='json')==doc['composition']
    assert load_budget() is DEFAULT_BUDGET
    assert direct.StageLimits is StageLimits and direct.StageBudget is StageBudget
    assert direct.CompositionBudget is CompositionBudget
    basic=StageBudget(request_limit=16,tool_calls_limit=20,total_tokens_limit=128000,timeout_seconds=240)
    assert basic.slack_tool_calls==doc['stage_defaults']['slack_tool_calls']
    assert basic.tokens_per_request==doc['stage_defaults']['tokens_per_request']
    assert DEFAULT_BUDGET.author_output_retries==2 and DEFAULT_BUDGET.output_retries==1
    assert DEFAULT_BUDGET.control_authoring.limits(1,3,2).model_dump()==dict(
        request_limit=10,tool_calls_limit=6,total_tokens_limit=120000,timeout_seconds=900,
        read_windows=1,work_tool_calls=3,ceilings=())


def test_explicit_yaml_override_has_distinct_effective_identity_and_json_parity(tmp_path):
    override={'author_output_retries':1,'setup_commands':8,
        'control_authoring':{'request_limit':12,'tool_calls_limit':10,'total_tokens_limit':100000,'timeout_seconds':800}}
    y=tmp_path/'budget.yaml';j=tmp_path/'budget.json'
    y.write_text(yaml.safe_dump(override));j.write_text(json.dumps(override))
    a=load_budget(y);b=load_budget(j)
    assert a==b and a.environment==DEFAULT_BUDGET.environment
    assert a.control_authoring.request_limit==12
    assert budget_sha256(a)!=budget_sha256(DEFAULT_BUDGET)
    assert BUDGET_POLICY_SHA256==__import__('hashlib').sha256(Path('src/corsair/policy/budget.yaml').read_bytes()).hexdigest()
    assert load_budget().author_output_retries==2
    with pytest.raises(FileNotFoundError):load_budget(tmp_path/'missing-budget.yaml')
    y.write_text('')
    with pytest.raises(ValidationError):load_budget(y)


@pytest.mark.parametrize('value',[
    {'control_authring':{}},{'author_output_retries':3},{'output_retries':2},{'setup_commands':True},
    {'control_authoring':{'request_limit':0,'tool_calls_limit':20,'total_tokens_limit':128000,'timeout_seconds':900}},
    {'control_authoring':{'request_limit':20,'tool_calls_limit':20,'total_tokens_limit':128000,'timeout_seconds':900,'repair_loop':True}},
])
def test_budget_yaml_unknown_roles_fields_and_ranges_fail_closed(tmp_path,value):
    p=tmp_path/'budget.yaml';p.write_text(yaml.safe_dump(value))
    with pytest.raises(ValidationError):load_budget(p)


def test_defaults_validate_under_subclasses_and_native_model_copy_semantics():
    class Checked(CompositionBudget):
        @model_validator(mode='after')
        def paired_retries(self):
            if self.author_output_retries<self.output_retries:
                raise ValueError('author retries less than common retries')
            return self
    budget=Checked()
    assert budget.model_dump()==DEFAULT_BUDGET.model_dump()
    with pytest.raises(ValidationError):Checked(author_output_retries=0)
    copied=budget.model_copy(update={'setup_commands':7})
    assert isinstance(copied,Checked) and copied.setup_commands==7
    assert copied.control_authoring==DEFAULT_BUDGET.control_authoring


def test_explicit_inference_yaml_named_and_legacy_json_parity(tmp_path):
    profile={'models':{'named':{'provider':'bedrock','model_name':'operator-choice','region':'us-east-1'}},
             'agents':{'control_authoring':'named'}}
    y=tmp_path/'model.yaml';j=tmp_path/'model.json'
    y.write_text(yaml.safe_dump(profile));j.write_text(json.dumps(profile))
    assert load_inference(y)==load_inference(j)
    assert load_inference(y).resolve('control_authoring').model_name=='operator-choice'
    with pytest.raises(ValueError,match='no model configured'):load_inference(y).resolve('exploit_authoring')
    legacy={'server':'vllm','base_url':'https://model.example.invalid/v1','model_name':'legacy-explicit'}
    y.write_text(yaml.safe_dump(legacy));j.write_text(json.dumps(legacy))
    assert load_inference(y)==load_inference(j)


def test_model_example_is_inert_and_unknown_provider_roles_rejected(tmp_path):
    config=load_inference(Path('src/corsair/policy/model.yaml'))
    assert config.default is None and config.resolve('planning').base_url=='https://model.example.invalid/v1'
    raw=config.model_dump(mode='json');raw['agents']['control_authring']='operator-example'
    p=tmp_path/'model.yml';p.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValidationError):load_inference(p)
    with pytest.raises(FileNotFoundError):load_inference(tmp_path/'missing.yaml')
    p.write_text('!!python/object/apply:os.system ["echo forbidden"]')
    with pytest.raises(yaml.constructor.ConstructorError):load_inference(p)
