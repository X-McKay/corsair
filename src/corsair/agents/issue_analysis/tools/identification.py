"""Bounded saved-source windows: the tool computes EOF, the model selects a start."""

from ...source.tools import window_source_tools


def identification_tools():
    return window_source_tools("issue_identification_source")
