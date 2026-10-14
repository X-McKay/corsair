"""Trusted operator policy: native typed ceilings with packaged YAML defaults."""
from copy import deepcopy
from hashlib import sha256
from importlib.resources import files
import json
from pathlib import Path
from typing import Literal
import yaml
from pydantic import ConfigDict, Field
from pydantic_ai.usage import UsageLimits
from corsair.agents.source.contracts import Contract

_POLICY_BYTES = files('corsair.policy').joinpath('budget.yaml').read_bytes()
_RAW_POLICY = yaml.safe_load(_POLICY_BYTES)
BUDGET_POLICY_SHA256 = sha256(_POLICY_BYTES).hexdigest()


def _stage_default(name):
    return deepcopy(_RAW_POLICY['stage_defaults'][name])


def _composition_default(name):
    return deepcopy(_RAW_POLICY['composition'][name])


class StageLimits(Contract):
    """One stage run's caps, derived from its own input and recorded in its receipt (SPEC-0043)."""
    request_limit: int = Field(strict=True, gt=0)
    tool_calls_limit: int = Field(strict=True, ge=0)
    total_tokens_limit: int = Field(strict=True, gt=0)
    timeout_seconds: float = Field(gt=0, allow_inf_nan=False)
    # Derivation: windows needed to read the stage's readable inputs once, plus input-sized work calls.
    read_windows: int = Field(strict=True, ge=0)
    work_tool_calls: int = Field(strict=True, ge=0)
    # Caps the operator's ceiling set below what the derivation gave, so a stop names its real source.
    ceilings: tuple[Literal["request_limit", "tool_calls_limit", "total_tokens_limit"], ...] = ()

    def usage_limits(self) -> UsageLimits:
        return UsageLimits(request_limit=self.request_limit, tool_calls_limit=self.tool_calls_limit,
                           total_tokens_limit=self.total_tokens_limit)


class StageBudget(Contract):
    """Operator-owned per-stage ceilings and derivation; the provider configuration owns the response cap.

    A run's tool calls are its read windows plus its work calls plus ``slack_tool_calls``; requests are
    those calls plus the output request and its retries plus one; tokens are ``tokens_per_request`` per
    request. Each is capped by the ceiling here, so a derived cap never exceeds what the operator admitted.
    """
    request_limit: int = Field(strict=True, gt=0, le=64)
    tool_calls_limit: int = Field(strict=True, ge=0, le=48)
    total_tokens_limit: int = Field(strict=True, gt=0, le=262144)
    timeout_seconds: float = Field(gt=0, le=1800, allow_inf_nan=False)
    slack_tool_calls: int = Field(default_factory=lambda: _stage_default("slack_tool_calls"), strict=True, ge=0, le=8)
    tokens_per_request: int = Field(default_factory=lambda: _stage_default("tokens_per_request"), strict=True, gt=0, le=32768)

    def limits(self, read_windows: int, work_tool_calls: int, output_retries: int) -> StageLimits:
        derived_tools = read_windows + work_tool_calls + self.slack_tool_calls
        tools = min(derived_tools, self.tool_calls_limit)
        derived_requests = tools + output_retries + 2
        requests = min(derived_requests, self.request_limit)
        derived_tokens = requests * self.tokens_per_request
        clamped = (("tool_calls_limit", derived_tools > self.tool_calls_limit),
                   ("request_limit", derived_requests > self.request_limit),
                   ("total_tokens_limit", derived_tokens > self.total_tokens_limit))
        return StageLimits(request_limit=requests, tool_calls_limit=tools,
                           total_tokens_limit=min(derived_tokens, self.total_tokens_limit),
                           timeout_seconds=self.timeout_seconds, read_windows=read_windows,
                           work_tool_calls=work_tool_calls, ceilings=tuple(name for name, hit in clamped if hit))


class CompositionBudget(Contract):
    """Operator ceilings and retry allowances from packaged budget.yaml, never repository task data."""
    model_config = ConfigDict(extra='forbid', frozen=True, validate_default=True)
    environment: StageBudget = Field(default_factory=lambda: _composition_default("environment"))
    identification: StageBudget = Field(default_factory=lambda: _composition_default("identification"))
    planning: StageBudget = Field(default_factory=lambda: _composition_default("planning"))
    control_authoring: StageBudget = Field(default_factory=lambda: _composition_default("control_authoring"))
    exploit_authoring: StageBudget = Field(default_factory=lambda: _composition_default("exploit_authoring"))
    assessment: StageBudget = Field(default_factory=lambda: _composition_default("assessment"))
    setup_commands: int = Field(default_factory=lambda: _composition_default("setup_commands"), strict=True, ge=1, le=16)
    dev_runs: int = Field(default_factory=lambda: _composition_default("dev_runs"), strict=True, ge=1, le=5)
    output_retries: int = Field(default_factory=lambda: _composition_default("output_retries"), strict=True, ge=0, le=1)
    author_output_retries: int = Field(default_factory=lambda: _composition_default("author_output_retries"), strict=True, ge=0, le=2)
    admission_refusals: int = Field(default_factory=lambda: _composition_default("admission_refusals"), strict=True, ge=0, le=2)


class _StageDefaults(Contract):
    slack_tool_calls: int = Field(strict=True, ge=0, le=8)
    tokens_per_request: int = Field(strict=True, gt=0, le=32768)


class _PackagedBudgetPolicy(Contract):
    stage_defaults: _StageDefaults
    composition: CompositionBudget


DEFAULT_BUDGET = _PackagedBudgetPolicy.model_validate(_RAW_POLICY).composition


def load_budget(path: Path | None = None) -> CompositionBudget:
    """The trusted packaged default, or an explicitly operator-selected flat budget override.

    Unspecified root fields use the same packaged defaults as CompositionBudget(). A provided
    stage still requires its four ceilings, matching the existing constructor contract.
    No task-controlled paths or discovery fallback are admitted here.
    """
    if path is None:
        return DEFAULT_BUDGET
    path = Path(path)
    text = path.read_text()
    value = yaml.safe_load(text) if path.suffix.lower() in ('.yaml', '.yml') else json.loads(text)
    return CompositionBudget.model_validate(value)


def budget_sha256(budget: CompositionBudget) -> str:
    """Identity of effective validated budget values, distinct from the default resource digest."""
    return sha256(json.dumps(budget.model_dump(mode='json'), sort_keys=True, separators=(',', ':')).encode()).hexdigest()
