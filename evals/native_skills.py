"""Scripted eval plumbing that asks the real SDK to activate native skills."""
from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart


def load_skills(messages, info, skill_ids):
    """Return real capability calls before a fixture's normal trajectory, never forged returns."""
    if not any(tool.name == 'load_capability' for tool in info.function_tools):
        return None
    successful = {part.tool_call_id for message in messages for part in message.parts
                  if isinstance(part, ToolReturnPart) and part.tool_name == 'load_capability'}
    loaded = {part.args_as_dict().get('id') for message in messages for part in message.parts
              if isinstance(part, ToolCallPart) and part.tool_name == 'load_capability'
              and part.tool_call_id in successful}
    pending = [name for name in skill_ids if name not in loaded]
    if not pending:
        return None
    return ModelResponse(parts=[ToolCallPart('load_capability', {'id': name}, tool_call_id='skill-' + name)
                                for name in pending])
