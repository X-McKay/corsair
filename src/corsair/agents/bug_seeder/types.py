"""Typed bug-seeding proposal output."""

from pydantic import Field

from corsair.domain.case import Frozen, SafePath


class SeededBug(Frozen):
    target_file: SafePath
    git_diff: str = Field(min_length=1, max_length=16_000)
    vulnerability_class: str = Field(min_length=1, max_length=128)
    hint_prompt: str = Field(min_length=1, max_length=2_000)
