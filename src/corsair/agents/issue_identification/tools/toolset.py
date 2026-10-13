"""Toolset binding for both identification modes, in offered order.

Both modes reuse the shared confined source readers rather than copying them; each binds
its own stable toolset id (its durable activity identity).
"""

from ...source.repository_tools import repository_source_tools
from ...source.tools import window_source_tools
from ...toolset_identity import toolset_sha256

TOOLSET_ID = "issue_identification_source"
REPOSITORY_TOOLSET_ID = "issue_identification_repository_source"


def identification_tools():
    """Bounded saved-source windows: the tool computes EOF, the model selects a start."""
    return window_source_tools(TOOLSET_ID)


def repository_tools():
    """List, search and read over a saved repository commit, withdrawn when the run byte budget is spent."""
    return repository_source_tools(REPOSITORY_TOOLSET_ID)


TOOLSET_SHA256 = toolset_sha256(identification_tools())
REPOSITORY_TOOLSET_SHA256 = toolset_sha256(repository_tools())
