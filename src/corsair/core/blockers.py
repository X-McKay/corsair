"""Operator-owned guidance shared by runtime admission and environment setup.

No raw output or command tokens: evidence references point to retained private receipts.
"""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Blocker(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    summary: str
    certainty: Literal["observed", "reported", "unknown"]
    owner: Literal["operator", "developer"]
    actions: tuple[str, ...] = Field(min_length=1)
    evidence: tuple[str, ...] = ()

    def render(self) -> str:
        return "\n".join((f"[{self.code}] {self.summary} ({self.certainty}; {self.owner})",
                          *(f"- {a}" for a in self.actions),
                          *(f"Evidence: {e}" for e in self.evidence)))
