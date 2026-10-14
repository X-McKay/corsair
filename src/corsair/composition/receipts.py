"""Receipts of one chain run, independent of what any agent later reads: every native runner observation (journal),
each stage attempt and the run's result, as JSON; and each stage's prompt, configuration, skill and toolset identity.
Shared by the product investigation entry and the evals."""
import base64
from dataclasses import asdict, fields, is_dataclass
from hashlib import sha256
import json
import threading

from pydantic import BaseModel, TypeAdapter
from pydantic_ai.messages import ModelMessage
from pydantic_ai.usage import RunUsage

from corsair.agents.environment import agent as environment
from corsair.agents.evidence_assessment import agent as assessment
from corsair.agents.issue_identification import agent as identification
from corsair.agents.control_authoring import agent as control_authoring
from corsair.agents.exploit_authoring import agent as exploit_authoring
from corsair.agents.test_planning import agent as planning
from corsair.agents.test_planning.skills import SKILL_SHA256 as PLANNING_SKILL

from corsair.agents.provider import LocalModelConfig
from corsair.inference.config import InferenceConfig, inference_config

from .direct import DirectRun

STAGES = ("identification", "planning", "control_authoring", "exploit_authoring", "assessment")
# A case that carries setup source runs the environment stage first (SPEC-0068); the fixture carries none.
AGENT_STAGES = ("environment",) + STAGES
# Per-stage request controls an operator profile may set on top of the base provider configuration.
PROFILE_FIELDS = {"response_token_limit", "thinking_mode", "thinking_token_budget", "timeout_seconds"}




def stage_configs(base: LocalModelConfig | InferenceConfig, profiles: dict, stages=STAGES) -> dict:
    """Each stage's provider configuration: the base with that stage's profile fields, revalidated."""
    if not isinstance(profiles, dict) or set(profiles) - set(AGENT_STAGES) or any(
            not isinstance(fields, dict) or set(fields) - PROFILE_FIELDS for fields in profiles.values()):
        raise ValueError(f"stage profiles map stages {AGENT_STAGES} to fields {sorted(PROFILE_FIELDS)}")
    resolved = ({stage: base for stage in stages} if isinstance(base, LocalModelConfig)
                else {stage: inference_config(base).resolve(stage) for stage in stages})
    return {stage: type(profile).model_validate(profile.model_dump() | profiles.get(stage, {}))
            for stage, profile in resolved.items()}


# Per-stage identity as each stage's own eval reports it (SPEC-0044, SPEC-0052).
VERSION_FIELDS = ("prompt_version", "config_version", "skill_sha256", "toolset_sha256")
VERSIONS = {
    "environment": (environment.PROMPT_VERSION, environment.CONFIG_VERSION, environment.SKILL_SHA256, environment.TOOLSET_SHA256),
    "identification": (identification.PROMPT_VERSION, identification.CONFIG_VERSION, identification.SKILL_SHA256,
                       identification.TOOLSET_SHA256),
    "planning": (planning.PROMPT_VERSION, planning.CONFIG_VERSION, PLANNING_SKILL, planning.TOOLSET_SHA256),
    "control_authoring": (control_authoring.PROMPT_VERSION, control_authoring.CONFIG_VERSION, control_authoring.SKILL_SHA256, control_authoring.TOOLSET_SHA256),
    "exploit_authoring": (exploit_authoring.PROMPT_VERSION, exploit_authoring.CONFIG_VERSION, exploit_authoring.SKILL_SHA256, exploit_authoring.TOOLSET_SHA256),
    "assessment": (assessment.PROMPT_VERSION, assessment.CONFIG_VERSION, assessment.SKILL_SHA256,
                   assessment.TOOLSET_SHA256),
}

# Bind identity to the same package spec loaded by each factory, rather than a later file read.
_MANIFESTS = {
    "environment": environment.MANIFEST_IDENTITY,
    "identification": identification.MANIFEST_IDENTITY,
    "planning": planning.MANIFEST_IDENTITY,
    "control_authoring": control_authoring.MANIFEST_IDENTITY,
    "exploit_authoring": exploit_authoring.MANIFEST_IDENTITY,
    "assessment": assessment.MANIFEST_IDENTITY,
}
VERSION_FIELDS += ("spec_sha256", "capability_selection_sha256", "factory_source_sha256", "shared_helper_source_sha256")
VERSIONS = {stage: version + tuple(_MANIFESTS[stage][key] for key in VERSION_FIELDS[-4:])
            for stage, version in VERSIONS.items()}


def encode(value):
    """Lossless JSON for native runner observations: dataclasses by field, bytes with digest and base64."""
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: encode(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, bytes):
        return {"sha256": sha256(value).hexdigest(), "size": len(value), "base64": base64.b64encode(value).decode()}
    if isinstance(value, (tuple, list)):
        return [encode(item) for item in value]
    if isinstance(value, dict):
        return {str(key): encode(item) for key, item in value.items()}
    if isinstance(value, BaseException):
        return {"type": type(value).__name__, "detail": str(value)[:4096], "receipt": encode(getattr(value, "receipt", None))}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


class Journal:
    """Wraps the operator's runners and keeps every complete native observation, failed ones included,
    with its purpose and operation, independently of what any agent later reads."""
    def __init__(self, runners):
        self.runners, self.entries = runners, []
        self._idle = threading.Condition()
        self._running = 0

    def drain(self, seconds: float) -> bool:
        """Wait for runner calls still in flight, e.g. a development run whose stage timed out in its worker
        thread; True when none remain. Their entries are only complete once they return."""
        with self._idle:
            return self._idle.wait_for(lambda: self._running == 0, timeout=seconds)

    def __call__(self, purpose):
        inner = self.runners(purpose)
        journal = self

        class Recorded:
            def run(self, patch, *, control_test_id, security_test_id, discovery_command, operation, witness=None):
                entry = {"purpose": purpose, "operation": str(operation), "patch_sha256": patch.sha256,
                         "witness_request": encode(witness), "observed": None, "failure": None}
                with journal._idle:
                    journal.entries.append(entry)
                    journal._running += 1
                try:
                    observed = inner.run(patch, control_test_id=control_test_id, security_test_id=security_test_id,
                                         discovery_command=discovery_command, operation=operation, witness=witness)
                except BaseException as exc:
                    entry["failure"] = encode(exc)
                    raise
                else:
                    entry["observed"] = encode(observed)
                    return observed
                finally:
                    with journal._idle:
                        journal._running -= 1
                        journal._idle.notify_all()
        return Recorded()


def _dump(value):
    return None if value is None else json.loads(value.model_dump_json())


def result_record(run: DirectRun) -> dict:
    executions = [{"revision": e.revision, "operation": str(e.operation),
                   "failure": None if e.failure is None else f"{type(e.failure).__name__}: {e.failure}",
                   "failure_layer": e.observed.failure_layer if e.observed else None,
                   "cleanup": e.observed.cleanup if e.observed else None,
                   "discovered": list(e.observed.discovery.test_ids) if e.observed and e.observed.discovery else [],
                   "cases": [{"test_id": c.test_id, "outcome": c.outcome,
                              "failure": asdict(c.failure) if c.failure else None}
                             for c in (e.observed.execution.cases if e.observed and e.observed.execution else ())],
                   "native_exit": (e.observed.execution.receipt.native_exit
                                   if e.observed and e.observed.execution and e.observed.execution.receipt else None)}
                  for e in run.executions]
    return {"stopped_at": run.stopped_at, "reason": run.reason, "runtime": _dump(run.runtime),
            "environment": _dump(run.environment), "identification": _dump(run.identification),
            "plan": _dump(run.plan), "patch": _dump(run.patch), "observation_plan": _dump(run.observation_plan),
            "executions": executions, "gate": _dump(run.gate), "assessment": _dump(run.assessment),
            "validity_review": _dump(run.validity_review),
            "witnesses": [{"witness": _dump(w.witness), "sandbox_events": None if w.sandbox_events is None else
                           [_dump(e) for e in w.sandbox_events], "reason": w.reason} for w in run.witnesses],
            "limitations": list(run.limitations)}


def attempt_record(attempt) -> dict:
    return {"stage": attempt.stage, "elapsed_seconds": attempt.elapsed_seconds,
            "failure": None if attempt.failure is None else {"type": type(attempt.failure).__name__,
                                                             "detail": str(attempt.failure)[:4096]},
            "output": _dump(attempt.output) if hasattr(attempt.output, "model_dump_json") else None,
            "usage": TypeAdapter(RunUsage).dump_python(attempt.usage, mode="json"),
            "limits": _dump(attempt.limits) if attempt.limits is not None else None,
            "exhausted": _dump(attempt.exhausted) if attempt.exhausted is not None else None,
            "tool_cap_reached": attempt.tool_cap_reached,
            "messages": TypeAdapter(list[ModelMessage]).dump_python(list(attempt.messages), mode="json")}
