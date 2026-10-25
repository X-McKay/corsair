"""Concrete auditor tool composition for one fresh ADK episode."""

from __future__ import annotations

from google.adk.tools.skill_toolset import SkillDiscoveryMode, SkillToolset

from corsair.agents.resources import load_agent_spec, load_runtime_skills


def build_auditor_toolset() -> list[SkillToolset]:
    """Return only the auditor's finite packaged procedural skill loader."""

    spec = load_agent_spec("auditor")
    if spec.source_tools:
        raise ValueError("auditor metadata must not grant source tools")
    return [
        SkillToolset(
            skills=load_runtime_skills("auditor"),
            discovery_mode=SkillDiscoveryMode.EAGER,
            tool_filter=list(spec.loader_tools),
        )
    ]
