"""Typed runtime dependencies passed to the producer SDK agent."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from corsair.domain.verification import Evaluation, Verdict
from corsair.ports.sandbox import Sandboxes
from corsair.ports.verification import Verification

SKILLS_DIR = Path(__file__).with_name("skills")
NEGATIVE_THRESHOLD = 2
"""Operator-owned: distinct clean negatives that end a run as LIKELY_NOT_EXPLOITABLE (K4)."""


@dataclass
class ProducerDeps:
    verification: Verification
    backend: Sandboxes
    work: str
    skills_dir: Path
    allowed_skills: tuple[str, ...]
    max_submissions: int = 4
    max_bash_calls: int = 12
    negative_threshold: int = NEGATIVE_THRESHOLD
    evaluations: list[Evaluation] = field(default_factory=list)
    verdict: Verdict | None = None
    bash_calls: int = 0
    checkpoint: Callable[[Evaluation], None] | None = None
    observations: list[dict] = field(default_factory=list)
