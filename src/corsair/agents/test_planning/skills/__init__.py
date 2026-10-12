"""One mandatory operator-owned stage skill, loaded before any model request.

No skill discovery, user paths, script execution or workspace access is exposed.
The native Capability supplies this exact text eagerly on every stage run.
"""

from hashlib import sha256
from pathlib import Path

SKILL_ID = "plan-two-tests"
SKILL_PATH = Path(__file__).parent / SKILL_ID / "SKILL.md"
SKILL_BYTES = SKILL_PATH.read_bytes()
SKILL_TEXT = SKILL_BYTES.decode("utf-8")
SKILL_SHA256 = sha256(SKILL_BYTES).hexdigest()
