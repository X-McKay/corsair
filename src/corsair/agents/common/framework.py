"""Framework guidance text for agents that need it (Investigator, Builder, Probers).

Framework skills live at ``src/corsair/skills/frameworks/<name>/SKILL.md`` and are the only place language and
framework knowledge is written down. A runtime row names its skill; the text is handed to an agent as guidance
data. A missing skill is not an error: the agent works without it and the absence is visible in its prompt.
"""
from __future__ import annotations

import re
from pathlib import Path

FRAMEWORK_SKILLS = Path(__file__).resolve().parents[2] / "skills" / "frameworks"
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def framework_guidance(skill: str, *, root: Path = FRAMEWORK_SKILLS) -> str | None:
    """The SKILL.md text for ``skill``, or None when the name is malformed or no such skill exists."""
    if not _NAME.match(skill) or ".." in skill:
        return None
    path = root / skill / "SKILL.md"
    return path.read_text(encoding="utf-8") if path.is_file() else None


def guidance_block(skill: str, *, root: Path = FRAMEWORK_SKILLS) -> str:
    """Prompt section with the framework guidance, or a plain statement that none is available."""
    text = framework_guidance(skill, root=root)
    if text is None:
        return f"Framework guidance for '{skill}': none available; rely on the repository's own conventions."
    return f"Framework guidance for '{skill}':\n<framework_guidance>\n{text.strip()}\n</framework_guidance>"
