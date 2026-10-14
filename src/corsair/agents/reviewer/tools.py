"""The Reviewer's tools: the native Harness ``FileSystem``, read-only, over the revision's tree (see
``agents/probing/source.py``). The two frozen drafts are in the prompt with line numbers, not on disk.

No tool runs anything or reads any execution result: the review is outcome-blind by construction.
"""
from ..probing.source import TOOL_NAMES

__all__ = ["TOOL_NAMES"]
