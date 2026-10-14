"""Control Prober (stage 5)."""
from .agent import NAME, SPEC, create_agent
from .stage import probe

__all__ = ["NAME", "SPEC", "create_agent", "probe"]
