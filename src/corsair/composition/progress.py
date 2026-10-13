"""SPEC-0072: run activity as typed events, for a view such as the terminal display; evidence files stay the record.

``run_chain`` reports stage boundaries, revision runs and the gate; inside an agent stage PydanticAI's own
capability hooks report model turns, tool calls, retries and model errors. Every text field is cleaned here, once:
control characters are removed (repository and model text cannot drive a terminal), long text is cut and values
under secret-like names are masked. Provider configuration is never an event. Observing is opt-in: with no
observer the chain and its agents run exactly as before.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import json
import re
from time import perf_counter
from typing import Any, Callable, Iterator, Literal

from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.exceptions import ToolRetryError


@dataclass(frozen=True)
class Usage:
    """What a stage has spent against its caps so far; None where the cap or count is unknown."""
    requests: int
    tool_calls: int
    tokens: int
    elapsed_seconds: float
    request_limit: int | None = None
    tool_calls_limit: int | None = None
    tokens_limit: int | None = None
    timeout_seconds: float | None = None


@dataclass(frozen=True)
class StageStarted:
    stage: str


@dataclass(frozen=True)
class StageEnded:
    """``ready``: the run goes on past this stage. ``stopped``: the run ends here with ``reason``."""
    stage: str
    outcome: Literal["ready", "stopped"]
    detail: str
    usage: Usage | None = None


@dataclass(frozen=True)
class ModelTurn:
    """One model response in an agent stage: the tools it asked for, whether it gave the stage's final output, and
    the stage's spend after it."""
    stage: str
    turn: int
    tools: tuple[str, ...]
    answered: bool
    usage: Usage


@dataclass(frozen=True)
class ToolCalled:
    stage: str
    tool: str
    arguments: str
    call_id: str = ""


@dataclass(frozen=True)
class ToolReturned:
    """``retry``: the tool asked the model to try again; ``error``: the tool raised and the stage fails."""
    stage: str
    tool: str
    outcome: Literal["ok", "retry", "error"]
    detail: str
    elapsed_seconds: float
    call_id: str = ""  # The ToolCalled it answers; calls in one turn may finish in any order


@dataclass(frozen=True)
class Retry:
    """The model's tool arguments or final output were refused and it was asked again."""
    stage: str
    target: Literal["tool arguments", "output"]
    name: str
    detail: str


@dataclass(frozen=True)
class ModelFailed:
    stage: str
    kind: str
    detail: str


@dataclass(frozen=True)
class RevisionStarted:
    revision: str


@dataclass(frozen=True)
class RevisionEnded:
    revision: str
    outcome: Literal["ran", "refused"]
    detail: str


@dataclass(frozen=True)
class GateDecided:
    verdict: str


@dataclass(frozen=True)
class RunEnded:
    stopped_at: str | None
    reason: str
    verdict: str | None


RunEvent = (StageStarted | StageEnded | ModelTurn | ToolCalled | ToolReturned | Retry | ModelFailed
            | RevisionStarted | RevisionEnded | GateDecided | RunEnded)
RunObserver = Callable[[RunEvent], None]


def ignore(event: RunEvent) -> None:
    """The observer of a run nobody watches."""


_observer: ContextVar[RunObserver | None] = ContextVar("corsair_run_observer", default=None)


@contextmanager
def observing(observer: RunObserver) -> Iterator[RunObserver]:
    """Every direct run started inside this block, in this context, reports to ``observer``."""
    token = _observer.set(observer)
    try:
        yield observer
    finally:
        _observer.reset(token)


def current_observer() -> RunObserver | None:
    return _observer.get()


# C0/C1 controls, CSI sequences and the Unicode marks that reorder a line (bidi overrides and isolates).
CONTROL = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|[\x00-\x08\x0b-\x1f\x7f-\x9f\u200e\u200f\u202a-\u202e\u2066-\u2069]")
SECRET_WORD = r"token|secret|password|passwd|pwd|api[_-]?key|access[_-]?key|private[_-]?key|authorization|credential|cookie"
SECRET_NAME = re.compile(SECRET_WORD, re.I)
CREDENTIAL = r"(?=[A-Za-z._~+/=-]*[0-9])[A-Za-z0-9._~+/=-]{8,}"
SECRETS = (
    # URL userinfo: https://user:pass@host
    (re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s@]+@"), r"\1[masked]@"),
    # An Authorization header's whole value, whatever its scheme or length
    (re.compile(r"(?i)\b((?:proxy-)?authorization)(\s*[=:]\s*)[^\"',;]+"), r"\1\2[masked]"),
    # An authorization scheme and its credential: Bearer x, Basic x; token x and Digest x when x looks like one
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"), "[masked]"),
    (re.compile(rf"(?i)\b(token|digest)\s+{CREDENTIAL}"), "[masked]"),
    # <secret-like name>=value or <secret-like name>: value, in commands, headers, env and text
    (re.compile(rf"(?i)\b([A-Za-z0-9_.-]*(?:{SECRET_WORD})[A-Za-z0-9_.-]*)(\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;&\"']+)"),
     r"\1\2[masked]"),
    # Well-known credential prefixes and private key blocks
    (re.compile(r"\b(?:(?:sk|ghp|gho|ghs|ghu|github_pat|glpat|xox[abprs])[-_][A-Za-z0-9_-]{8,}|(?:AKIA|ASIA)[0-9A-Z]{16}"
                r"|AIza[0-9A-Za-z_-]{30,})"), "[masked]"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(-----END [A-Z ]*PRIVATE KEY-----|$)"), "[masked]"),
)


def clean(text: object, limit: int = 240) -> str:
    """One display line: no control characters or escape sequences, credential-shaped values masked, cut to
    ``limit`` characters."""
    line = CONTROL.sub("", " ".join(str(text).split()))
    for pattern, replacement in SECRETS:
        line = pattern.sub(replacement, line)
    return line if len(line) <= limit else line[:limit - 1] + "…"


def preview(arguments: Any, limit: int = 96) -> str:
    """Tool arguments as ``name=value`` pairs, values under secret-like names masked."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            return clean(arguments, limit)
    if not isinstance(arguments, dict):
        return clean(arguments, limit)
    pairs = []
    for name, value in arguments.items():
        shown = "[masked]" if SECRET_NAME.search(str(name)) else value if isinstance(value, (int, float, bool)) else (
            json.dumps(value) if isinstance(value, str) else f"<{type(value).__name__}>")
        pairs.append(f"{name}={shown}")
    return clean(", ".join(pairs), limit)


class Activity(AbstractCapability[Any]):
    """Observation only: each hook reports and hands its value on unchanged, or re-raises its error."""

    def __init__(self, stage: str, observe: RunObserver, limits: Any = None, started: float | None = None):
        super().__init__()
        self.stage, self.watcher, self.limits = stage, observe, limits
        self.started = perf_counter() if started is None else started

    def observe(self, event: RunEvent) -> None:
        # A failing view never fails the stage (SPEC-0072).
        try:
            self.watcher(event)
        except Exception:
            pass

    def usage(self, usage: Any, turn: int = 0) -> Usage:
        limits = self.limits
        return Usage(requests=max(usage.requests, turn), tool_calls=usage.tool_calls, tokens=usage.total_tokens,
                     elapsed_seconds=perf_counter() - self.started,
                     request_limit=limits and limits.request_limit, tool_calls_limit=limits and limits.tool_calls_limit,
                     tokens_limit=limits and limits.total_tokens_limit,
                     timeout_seconds=limits and limits.timeout_seconds)

    async def after_model_request(self, ctx, *, request_context, response):
        outputs = {tool.name for tool in request_context.model_request_parameters.output_tools}
        calls = [call.tool_name for call in response.tool_calls]
        answered = any(name in outputs for name in calls) or (not calls and response.text is not None)
        self.observe(ModelTurn(self.stage, ctx.run_step, tuple(clean(name, 64) for name in calls if name not in outputs),
                               answered, self.usage(ctx.usage, ctx.run_step)))
        return response

    async def on_model_request_error(self, ctx, *, request_context, error):
        self.observe(ModelFailed(self.stage, type(error).__name__, clean(error)))
        raise error

    async def wrap_tool_execute(self, ctx, *, call, tool_def, args, handler):
        name, started, call_id = clean(call.tool_name, 64), perf_counter(), call.tool_call_id or ""
        self.observe(ToolCalled(self.stage, name, preview(args), call_id))
        try:
            result = await handler(args)
        except ToolRetryError as retry:
            self.observe(ToolReturned(self.stage, name, "retry", clean(retry), perf_counter() - started, call_id))
            raise
        except Exception as error:
            self.observe(ToolReturned(self.stage, name, "error", clean(f"{type(error).__name__}: {error}"),
                                      perf_counter() - started, call_id))
            raise
        self.observe(ToolReturned(self.stage, name, "ok", "", perf_counter() - started, call_id))
        return result

    async def on_tool_validate_error(self, ctx, *, call, tool_def, args, error):
        self.observe(Retry(self.stage, "tool arguments", clean(call.tool_name, 64), _validation(error)))
        raise error

    async def on_output_validate_error(self, ctx, *, output_context, output, error):
        self.observe(Retry(self.stage, "output", "", _validation(error)))
        raise error


def _validation(error: BaseException) -> str:
    errors = getattr(error, "errors", None)
    if callable(errors):
        try:
            first = errors()[0]
            where = ".".join(str(part) for part in first.get("loc", ()))
            return clean(f"{len(errors())} error(s); {where + ': ' if where else ''}{first.get('msg', '')}", 160)
        except Exception:
            pass
    return clean(error, 160)
