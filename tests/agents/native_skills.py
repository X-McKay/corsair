"""Offline test models activate real SDK skill disclosure before their existing trajectory."""
from pydantic_ai.messages import LoadCapabilityReturnPart
from evals.native_skills import load_skills


def activate_skill(messages, info, skill_id, skill_text):
    body = skill_text.split('---', 2)[2].strip()
    activation = load_skills(messages, info, [skill_id])
    if activation is not None:
        assert body not in info.instructions
        return activation
    disclosed = [part.content.get('instructions', '') for message in messages for part in message.parts
                 if isinstance(part, LoadCapabilityReturnPart)]
    assert any(body in instructions for instructions in disclosed)
    return None
