"""Separate specialist instructions and skills with literal narrow input rendering."""
from hashlib import sha256
from pathlib import Path
from pydantic_ai.agent.spec import AgentSpec
from ..probe_authoring.skills import COMMON_SKILL_ID, COMMON_SKILL_TEXT, COMMON_SKILL_SHA256
_SPEC = AgentSpec.from_file(Path(__file__).with_name('agent.yaml'))
PROMPT_VERSION = _SPEC.metadata['prompt_version']
INSTRUCTIONS = _SPEC.instructions
CONTROL_SKILL_ID = 'control-probe'
CONTROL_SKILL_TEXT = (Path(__file__).parent / 'skills' / CONTROL_SKILL_ID / 'SKILL.md').read_text()
CONTROL_SKILL_SHA256 = sha256(CONTROL_SKILL_TEXT.encode()).hexdigest()

def prompt_for(inputs):
    return inputs.model_dump_json(exclude={'source_files': True}) + '\nReadable saved source: ' + ', '.join(s.path for s in inputs.source_files)


SKILL_ID = CONTROL_SKILL_ID
SKILL_SHA256 = sha256((CONTROL_SKILL_TEXT + COMMON_SKILL_TEXT).encode()).hexdigest()
