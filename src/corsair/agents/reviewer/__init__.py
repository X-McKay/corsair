"""Outcome-blind Reviewer (stage 6)."""
from .agent import NAME, SPEC, create_agent
from .stage import review

__all__ = ["NAME", "SPEC", "create_agent", "review"]
