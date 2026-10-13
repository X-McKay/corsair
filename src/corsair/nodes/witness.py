"""Execution-node witness capture (SPEC-0033): inject the operator probe, then map its record to gate input.

The probe source is repository-owned and pinned here by digest; it reaches the test interpreter only
through the runner's execution argv, replacing the operator's ``-m pytest``. Nothing here reads model
text: the target comes from the admitted identification, and the record is accepted only when its nonce,
probe digest, target and integrity flags match what the operator sent.
"""
from dataclasses import dataclass
import errno
from hashlib import sha256
import json
import posixpath
from pathlib import Path, PurePosixPath
import re
from typing import NamedTuple

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from corsair.core.disposition import SandboxEvent, Witness
from corsair.ports.test_runner import WitnessCapture, WitnessRequest

PROBE_SOURCE = (Path(__file__).with_name('witness_probe.py')).read_text(encoding='utf-8')
PROBE_SHA256 = sha256(PROBE_SOURCE.encode('utf-8')).hexdigest()
# Every operator probe beside this module (one per language driver, which injects it) writes the same record; a
# capture names the probe that ran, and only these digests are admitted.
PROBES = frozenset(sha256(path.read_text(encoding='utf-8').encode('utf-8')).hexdigest()
                   for path in Path(__file__).parent.glob('witness_probe.*'))
TOOL_ID = 4  # sys.monitoring ids 0-2 and 5 are reserved for debugger, coverage, profiler and optimizer
MAX_RECORD_BYTES = 65536
# Fixed bootstrap: the probe and its JSON config are the first two arguments; pytest gets the rest.
BOOTSTRAP = ('import hashlib, json, sys, types\n'
             'source, config = sys.argv[1], json.loads(sys.argv[2])\n'
             "probe = types.ModuleType('corsair_witness_probe')\n"
             "exec(compile(source, 'corsair_witness_probe', 'exec'), probe.__dict__)\n"
             'plugin = probe.Probe(hashlib.sha256(source.encode()).hexdigest(), config)\n'
             'import pytest\n'
             'raise SystemExit(int(pytest.main(sys.argv[3:], plugins=[plugin])))\n')
DENIALS = frozenset({errno.EACCES, errno.EPERM})
TOKEN = re.compile(r'^[A-Za-z0-9_.:-]{1,128}$')


def probe_argv(command: tuple[str, ...], request: WitnessRequest, *, root: str, record_path: str,
               nonce: str) -> tuple[str, ...]:
    """The operator command with its single ``-m pytest`` replaced by the probe bootstrap."""
    pairs = [i for i in range(len(command) - 1) if command[i:i + 2] == ('-m', 'pytest')]
    if len(pairs) != 1:
        raise ValueError('witness capture needs exactly one `-m pytest` in the operator command')
    config = json.dumps({'root': root, 'target_path': request.target_path, 'target_symbol': request.target_symbol,
                         'effect_name': request.effect_name, 'record_path': record_path, 'nonce': nonce, 'tool_id': TOOL_ID}, sort_keys=True)
    at = pairs[0]
    return command[:at] + ('-c', BOOTSTRAP, PROBE_SOURCE, config) + command[at + 2:]


class _Record(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)


class _OSError(_Record):
    type: str = Field(max_length=128)
    errno: int | None


class _Open(_Record):
    path: str | None = Field(max_length=512)
    planned: bool


class _TestRecord(_Record):
    entered: int = Field(ge=0)
    exits: tuple[str | None, ...] = Field(max_length=32)
    opens: tuple[_Open, ...] = Field(max_length=32)
    os_errors: tuple[_OSError, ...] = Field(max_length=32)
    truncated: bool
    complete: bool
    # Planned-file opens off the target's stack during the call (other threads, or after the first entry); None when the record predates the count.
    offstack_planned: int | None = Field(default=None, ge=0)
    # Planned-file opens the test function made itself after the first call (checking its own fixture); never the effect.
    body_planned: int | None = Field(default=None, ge=0)


class _Target(_Record):
    path: str
    symbol: str
    effect_name: str


class ProbeRecord(_Record):
    schema_: str = Field(alias='schema')
    nonce: str
    plugin_sha256: str
    target: _Target
    tool_registered: bool
    intact: bool
    unsupported: str | None = Field(max_length=256)
    tests: dict[str, _TestRecord] = Field(max_length=16)


@dataclass(frozen=True)
class WitnessEvidence:
    """Gate input for one run; ``witness`` and ``sandbox_events`` are both None when nothing is admitted."""
    witness: Witness | None
    sandbox_events: tuple[SandboxEvent, ...] | None
    reason: str


def _refused(reason: str) -> WitnessEvidence:
    return WitnessEvidence(None, None, reason)


ABSENCE = 'no_file_open'


class Calibration(NamedTuple):
    """The plan's control: its test id and the scratch-relative file its call must open (SPEC-0040)."""
    test_id: str
    subject: str


def _uncalibrated(record: 'ProbeRecord', control: Calibration | None) -> str | None:
    """Why the control does not show the probe recording the target's opens in this run, or None when it does.

    The control's call phase must be attributable (complete, paired, not truncated, the target entered) and hold
    an open, on the target's stack, of a path ending in the control's subject."""
    if control is None:
        return 'no control calibration was requested'
    test = record.tests.get(control.test_id)
    if test is None or not test.complete:
        return 'the control call phase was not observed to completion'
    if not test.entered or test.truncated or test.entered != len(test.exits):
        return 'the control call phase is not attributable to the target'
    parts = PurePosixPath(control.subject).parts
    if not any(o.path is not None and PurePosixPath(posixpath.normpath(o.path)).parts[-len(parts):] == parts
               for o in test.opens):
        return f'the control witness {control.subject!r} was not observed; the probe does not record this effect here'
    return None


def witness_evidence(capture: WitnessCapture | None, request: WitnessRequest,
                     security_test_id: str, *, planned_safe_behavior: str | None = None,
                     control: Calibration | None = None) -> WitnessEvidence:
    """Map the probe record for the security test's call phase to the SPEC-0027 witness, or refuse it.

    When the plan's safe behavior is the absence identity ``no_file_open`` (SPEC-0040), an attributed call
    phase without the planned open is that behavior, however the target exited, but only once ``control`` is
    observed as planned in the same run: an absence the control does not calibrate refuses the witness, so a
    facility or payload that never reaches the effect cannot pass as safe. An observed effect needs no
    calibration; it is its own evidence that the probe records it.
    """
    if capture is None:
        return _refused('no witness was requested or captured for this run')
    if capture.status != 'captured' or capture.artifact is None:
        return _refused(f'witness unavailable: {capture.detail}'[:512])
    if capture.request != request or capture.probe_sha256 not in PROBES:
        return _refused('witness capture used another target or probe')
    if capture.artifact.sha256 != sha256(capture.record).hexdigest():
        return _refused('witness record bytes differ from the stored artifact')
    try:
        record = ProbeRecord.model_validate_json(capture.record)
    except ValidationError as error:
        return _refused(f'witness record invalid: {error.error_count()} errors')
    if (record.schema_ != 'corsair-witness-v2' or record.nonce != capture.nonce
            or record.plugin_sha256 != capture.probe_sha256
            or (record.target.path, record.target.symbol, record.target.effect_name)
            != (request.target_path, request.target_symbol, request.effect_name)):
        return _refused('witness record does not belong to this run, probe or target')
    if record.unsupported is not None:
        return _refused(f'witness probe unsupported on this runtime: {record.unsupported}')
    if not (record.tool_registered and record.intact):
        return _refused('witness probe was not registered or its monitoring changed during the run')
    test = record.tests.get(security_test_id)
    if test is None or not test.complete:
        return _refused('the security test call phase was not observed to completion')
    if test.entered != len(test.exits) and not test.truncated:
        return _refused('target calls and exits do not pair; the call phase is not attributable')

    denials = [e for e in test.os_errors if e.errno in DENIALS]
    events = tuple(SandboxEvent(kind='policy_denial', phase='test', touches_witness_path=None) for _ in denials)
    # Only opens of the planned file are the effect; other files the target reads are recorded, not counted.
    planned = [o for o in test.opens if o.planned]
    if test.offstack_planned:
        effect = 'unknown'  # the planned file was opened off the target's stack; not attributable either way
    elif planned and len(denials) < len(test.os_errors):
        effect = 'unknown'  # an attempted open failed for another reason; the effect is not established
    elif planned:
        effect = 'observed'
    elif test.truncated:
        effect = 'unknown'  # a planned open may lie beyond the recorded cap
    else:
        effect = 'absent'
    exits = set(test.exits)
    safe = None
    if test.entered and not test.truncated and len(exits) == 1:
        (only,) = exits
        safe = only if only is not None and TOKEN.fullmatch(only) else None
    if (planned_safe_behavior == ABSENCE and effect == 'absent' and test.offstack_planned == 0
            and test.entered and not test.truncated and test.entered == len(test.exits)):
        if reason := _uncalibrated(record, control):
            return _refused(f'absence not calibrated: {reason}')
        safe = ABSENCE
    witness = Witness(artifact_sha256=capture.artifact.sha256, path_reached=test.entered > 0 or bool(planned),
                      effect=effect, safe_behavior=safe)
    return WitnessEvidence(witness, events, 'admitted')
