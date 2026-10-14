"""Fixture-only conversion of frozen final plans to the current named-component draft.

Frozen inputs and reference outputs retain their recorded bytes. Production drafts never
accept the serialized native identifiers this adapter reads.
"""
from copy import deepcopy

from corsair.ports.test_runner import TEST_ID, JavaTestId, JsTestId, PerlTestId, RubyTestId, names_test_in


def component_draft(plan: dict) -> dict:
    result = deepcopy(plan)
    if result.get('status') != 'ready':
        return result
    for role in ('control', 'security'):
        spec = result[role]
        identity = spec.pop('test_id', None)
        if identity is None:
            continue  # Current fixture drafts already supply named components.
        if not names_test_in(identity, spec['test_path']):
            raise ValueError('frozen reference test id does not name its recorded test path')
        if TEST_ID.fullmatch(identity):
            parts = identity.split('::')
            name, container = parts[-1], parts[1] if len(parts) == 3 else None
        else:
            parsed = None
            for parser in (RubyTestId, JsTestId, PerlTestId, JavaTestId):
                try:
                    candidate = parser.parse(identity)
                except ValueError:
                    continue
                path = candidate.source_path() if isinstance(candidate, JavaTestId) else candidate.path
                if path == spec['test_path']:
                    parsed = candidate
                    break
            if parsed is None:
                raise ValueError('frozen reference test id has no admitted native parser')
            name = parsed.method if isinstance(parsed, (RubyTestId, JavaTestId)) else parsed.name
            container = parsed.class_name if isinstance(parsed, (RubyTestId, JavaTestId)) else (
                parsed.suite if isinstance(parsed, JsTestId) else None)
        spec['test_name'] = name
        if container is not None:
            spec['test_container'] = container
    return result
