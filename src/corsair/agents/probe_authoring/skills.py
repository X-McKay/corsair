"""The shared native-probe procedure, read once by both independent authors."""
from hashlib import sha256
from pathlib import Path
COMMON_SKILL_ID = 'native-probe-boundary'
COMMON_SKILL_TEXT = (Path(__file__).parent/'skills'/COMMON_SKILL_ID/'SKILL.md').read_text(encoding='utf-8')
COMMON_SKILL_SHA256 = sha256(COMMON_SKILL_TEXT.encode()).hexdigest()
