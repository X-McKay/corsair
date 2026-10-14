"""Operator-owned identification skill bytes and provenance, one per source mode.

Native Skills publishes each fixed role catalog and discloses its body on activation.
"""

from hashlib import sha256
from pathlib import Path

SKILL_ID = "identify-issue"
SKILL_TEXT = (Path(__file__).parent / SKILL_ID / "SKILL.md").read_text()
SKILL_SHA256 = sha256(SKILL_TEXT.encode()).hexdigest()

REPOSITORY_SKILL_ID = "identify-issue-repository"
REPOSITORY_SKILL_TEXT = (Path(__file__).parent / REPOSITORY_SKILL_ID / "SKILL.md").read_text()
REPOSITORY_SKILL_SHA256 = sha256(REPOSITORY_SKILL_TEXT.encode()).hexdigest()
