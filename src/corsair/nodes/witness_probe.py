"""Operator witness probe for one pytest run; loaded by the runner's bootstrap, never by workload code.

Standard library and pytest hooks only: the bytes travel to the test interpreter as an argument and must
load on any admitted CPython (3.7+) and pytest (old-style hook wrapper, no ``pytest.ExitCode``). Observation
needs CPython 3.12+ (``sys.monitoring``; audit hooks are 3.8+ and ``co_qualname`` 3.11+): on an older runtime the
probe registers nothing, lets the run proceed and writes a record naming the runtime as unsupported. Native ``sys.monitoring`` events attribute calls, returns and unwinds to
the identified target function; native audit ``open`` events and raised ``OSError``s count only when the
target is on the calling stack and only during a test's call phase. The record is written once, after the
session, to an operator path; the host maps it to the gate's witness. It runs inside the test interpreter,
so it is tamper-evident (its own tool registration, events and the operator nonce are checked), not
tamper-proof against hostile test code.
"""
import json
import os
import sys

import pytest

SCHEMA = 'corsair-witness-v2'
TOOL_NAME = 'corsair-witness'
MAX_OPENS = 32
MAX_CALLS = 32
MAX_TESTS = 16


def _name(value):
    """Builtin exceptions by bare name (the planner's vocabulary), others qualified so a local lookalike never matches."""
    if not isinstance(value, BaseException):
        return None
    kind = type(value)
    return kind.__name__ if kind.__module__ == 'builtins' else f'{kind.__module__}.{kind.__qualname__}'


class Probe:
    def __init__(self, plugin_sha256, config):
        self.config = config
        self.target_file = os.path.realpath(os.path.join(config['root'], config['target_path']))
        self.symbol = config['target_symbol']
        self.effect_name = config['effect_name']
        self.record = {'schema': SCHEMA, 'nonce': config['nonce'], 'plugin_sha256': plugin_sha256,
                       'target': {'path': config['target_path'], 'symbol': self.symbol,
                                  'effect_name': self.effect_name},
                       'tool_registered': False, 'intact': False, 'unsupported': None, 'tests': {}}
        self.active = None
        # Keyed by identity with the code object kept alive: equal code objects from other files or
        # qualnames compare equal, so an equality-keyed cache would let a lookalike pass as the target.
        self.known = {}
        self.files = {}
        self.raised = []
        self.tool = config['tool_id']
        monitoring = getattr(sys, 'monitoring', None)
        if monitoring is None:
            self.record['unsupported'] = 'CPython {}.{}.{} has no sys.monitoring (3.12+)'.format(*sys.version_info[:3])
            return
        events = monitoring.events
        self.events = events.PY_START | events.PY_RETURN | events.PY_UNWIND | events.RAISE
        try:
            monitoring.use_tool_id(self.tool, TOOL_NAME)
        except ValueError:
            return
        self.record['tool_registered'] = True
        for event, callback in ((events.PY_START, self._start), (events.PY_RETURN, self._return),
                                (events.PY_UNWIND, self._unwind), (events.RAISE, self._raise)):
            monitoring.register_callback(self.tool, event, callback)
        monitoring.set_events(self.tool, self.events)
        sys.addaudithook(self._audit)

    def _target(self, code):
        entry = self.known.get(id(code))
        if entry is None or entry[0] is not code:
            filename = code.co_filename
            if filename not in self.files:
                self.files[filename] = os.path.realpath(filename) == self.target_file
            entry = (code, code.co_qualname == self.symbol and self.files[filename])
            self.known[id(code)] = entry
        return entry[1]

    def _on_stack(self, frame):
        while frame is not None:
            if self._target(frame.f_code):
                return True
            frame = frame.f_back
        return False

    @staticmethod
    def _loader_frame(frame):
        # Only the import system's own source and bytecode reads (io.open_code called directly from an
        # importlib loader frame) are excluded; code a module body runs during import still counts.
        return frame.f_code.co_filename.startswith(('<frozen importlib', '<frozen zipimport'))

    def _planned(self, path):
        if not isinstance(path, str):
            return False
        try:
            resolved = os.path.realpath(path)
        except (OSError, ValueError):
            resolved = path
        return self.effect_name in (os.path.basename(path), os.path.basename(resolved))

    def _test(self):
        return self.record['tests'].get(self.active) if self.active is not None else None

    def _start(self, code, offset):
        if not self._target(code):
            return sys.monitoring.DISABLE
        test = self._test()
        if test is not None:
            test['entered'] += 1
        return None

    def _end(self, code, outcome):
        test = self._test()
        if test is not None and self._target(code):
            if len(test['exits']) < MAX_CALLS:
                test['exits'].append(outcome)
            else:
                test['truncated'] = True

    def _return(self, code, offset, value):
        if not self._target(code):
            return sys.monitoring.DISABLE
        self._end(code, None)
        return None

    def _unwind(self, code, offset, exception):
        self._end(code, _name(exception))

    def _raise(self, code, offset, exception):
        test = self._test()
        frame = sys._getframe(1)
        if test is not None and isinstance(exception, OSError) and self._on_stack(frame):
            # RAISE fires again in every frame the exception propagates through; record it once, and never
            # for the import system's own path probing (its first frame is a loader frame).
            if any(seen is exception for seen in self.raised):
                return
            self.raised.append(exception)
            if self._loader_frame(frame):
                return
            if len(test['os_errors']) < MAX_OPENS:
                test['os_errors'].append({'type': _name(exception), 'errno': exception.errno})
            else:
                test['truncated'] = True

    def _audit(self, event, args):
        if event != 'open' or self.active is None:
            return
        test = self._test()
        frame = sys._getframe(1)
        if test is None or self._loader_frame(frame) or not self._on_stack(frame):
            return
        path = args[0] if args else None
        if isinstance(path, bytes):
            path = path.decode('utf-8', 'replace')
        if len(test['opens']) < MAX_OPENS:
            test['opens'].append({'path': str(path)[:512] if isinstance(path, (str, int)) else None,
                                  'planned': self._planned(path)})
        else:
            test['truncated'] = True

    # pytest hook: only the call phase is observed, so fixtures and teardown never count.
    # Old-style wrapper: new-style ``wrapper=True`` needs pluggy 1.1+, which older pytest releases may not have.
    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_call(self, item):
        tests = self.record['tests']
        if item.nodeid not in tests and len(tests) < MAX_TESTS:
            tests[item.nodeid] = {'entered': 0, 'exits': [], 'opens': [], 'os_errors': [], 'truncated': False,
                                  'complete': False}
        self.active = item.nodeid if item.nodeid in tests else None
        try:
            yield
        finally:
            if self.active is not None:
                tests[self.active]['complete'] = True
            self.active = None
            self.raised.clear()

    def pytest_sessionfinish(self, session, exitstatus):
        self.active = None
        if self.record['tool_registered']:
            monitoring = sys.monitoring
            self.record['intact'] = (monitoring.get_tool(self.tool) == TOOL_NAME
                                     and monitoring.get_events(self.tool) == self.events)
            monitoring.set_events(self.tool, 0)
        data = json.dumps(self.record, sort_keys=True).encode()
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
        try:
            descriptor = os.open(self.config['record_path'], flags, 0o600)
        except OSError:
            # Something else created the record path: the run itself fails rather than offering that file.
            session.exitstatus = 3  # pytest's internal-error status; ``pytest.ExitCode`` is pytest 5+
            return
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data)
