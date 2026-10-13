"""Bounded parsing of the JUnit Platform console launcher's `discover --details=flat` listing.

Each listed node ends with its unique id in parentheses. Test leaves are Jupiter methods without
parameters or JUnit 4 (Vintage) tests; any other leaf, or a count that disagrees with the launcher's
summary, makes the listing inexact. The listing is a workload claim about discovery, not attestation.
"""
import re

MAX_LISTING_BYTES = 65536
UID = re.compile(r'\((?P<uid>\[engine:[^()\s]*(?:\([^()\s]*\)[^()\s]*)*)\)$')
JUPITER = re.compile(r'\[engine:junit-jupiter\]/\[class:(?P<class_name>[\w.]+)\]/\[method:(?P<method>\w+)\(\)\]')
VINTAGE = re.compile(r'\[engine:junit-vintage\]/\[runner:(?P<class_name>[\w.]+)\]/\[test:(?P<method>\w+)\((?P=class_name)\)\]')
SUMMARY = re.compile(r'\[\s*(?P<count>\d+) tests found\s*\]')


def listed(stdout: bytes, *, max_bytes: int = MAX_LISTING_BYTES) -> tuple[tuple[str, str], ...] | None:
    """(class, method) for every discovered test, in listing order; None when the listing is not exact."""
    if type(stdout) is not bytes or not stdout or len(stdout) > max_bytes:
        return None
    try:
        lines = stdout.decode('utf-8').splitlines()
    except UnicodeError:
        return None
    tests, counts = [], [int(match['count']) for line in lines if (match := SUMMARY.fullmatch(line.strip()))]
    for line in lines:
        match = UID.search(line)
        if match is None or match['uid'].count('/[') < 2:
            continue  # engines, class containers, blank and summary lines
        leaf = JUPITER.fullmatch(match['uid']) or VINTAGE.fullmatch(match['uid'])
        if leaf is None:
            return None  # parametrized, nested, dynamic or another engine's test: not a plain method
        tests.append((leaf['class_name'], leaf['method']))
    if counts != [len(tests)]:
        return None
    return tuple(tests)
