"""The fixed next step printed beside a failed command (every CLI command's error path).

``Terminal.report_failure`` logs ``cli.failed`` with the sanitized error and, when the
failure belongs to a known class, one of these constant remedies; ``corsair doctor``
attaches the same remedies to its environment checks.
"""

import json
import sys
from typing import cast

from pydantic import ValidationError

from corsair.policies.target_binding import TargetBindingBlocked
from corsair.ports.sandboxing import SandboxUnavailable
from corsair.ports.scm import SourceAdmissionError

_TEMPORAL_REMEDY = (
    "Start Temporal (for example `temporal server start-dev`) or set temporal_address and "
    "temporal_namespace in --settings, then run `corsair doctor`."
)
_DOCKER_REMEDY = "Start the Docker daemon (or set DOCKER_HOST), then run `corsair doctor`."
_IMAGE_REMEDY = (
    "Build the trusted image with `just images`, or set image in --settings to a built tag, "
    "then run `corsair doctor`."
)
_JSON_REMEDY = "The file is not valid JSON; check it for truncation or an editing mistake."
_SOURCE_REMEDIES = (
    (
        "outside configured source_root",
        "Set source_root in --settings to a directory that contains the request's sources "
        "(the default is the current directory).",
    ),
    (
        "expected_digest",
        "The source tree differs from the request's frozen expected_digest. Restore that "
        "source, or write a new request for the changed source; never edit a frozen digest.",
    ),
    (
        "source path does not exist",
        "Check source.path in the request; it resolves relative to the request file.",
    ),
    (
        "configured source_root",
        "Set source_root in --settings to an existing, readable directory that is not a "
        "symbolic link.",
    ),
    (
        "limit",
        "Narrow the request's source path to the code under test, or review "
        "source_limit_bytes and source_limit_files in --settings.",
    ),
    (
        "are not admitted",
        "Remove symbolic links and special files from the source tree; only regular files "
        "and directories are admitted.",
    ),
)


def _module_error(error: BaseException, module: str, name: str) -> bool:
    """Match an SDK exception class only if its module is already loaded; never import it."""
    kind = getattr(sys.modules.get(module), name, None)
    return isinstance(kind, type) and isinstance(error, kind)


def failure_remedy(error: BaseException) -> str | None:
    """Return one fixed next step for a known failure class, or ``None``.

    The exception text is matched against fixed patterns but never echoed: every remedy is a
    constant, so it cannot carry credentials, endpoints or provider content. The original,
    sanitized error detail is still reported beside it.
    """
    text = str(error)
    if isinstance(error, ValidationError):
        if any(
            item["type"] == "json_invalid"
            for item in error.errors(include_input=False, include_url=False)
        ):
            return _JSON_REMEDY
        return (
            "Correct the fields named above; see docs/reference/configuration.md for settings "
            "and docs/reference/schemas.md for requests and submissions."
        )
    if isinstance(error, json.JSONDecodeError):
        return _JSON_REMEDY
    if isinstance(error, FileNotFoundError):
        return (
            "Check the path: command arguments and --settings resolve from the current "
            "directory, request source paths from the request file's directory."
        )
    if isinstance(error, IsADirectoryError | NotADirectoryError):
        return "Pass the path of a file, not a directory, and check each parent directory."
    if isinstance(error, PermissionError):
        return "Check file permissions: inputs must be readable and artifact_root writable."
    if isinstance(error, SourceAdmissionError):
        return next((remedy for pattern, remedy in _SOURCE_REMEDIES if pattern in text), None)
    if isinstance(error, SandboxUnavailable):
        return _IMAGE_REMEDY if "image" in text else _DOCKER_REMEDY
    if _module_error(error, "docker.errors", "ImageNotFound"):
        return _IMAGE_REMEDY
    if _module_error(error, "docker.errors", "DockerException"):
        return _DOCKER_REMEDY
    if _module_error(error, "temporalio.service", "RPCError"):
        # Already loaded whenever an RPCError exists; importing it eagerly costs ~0.3 s.
        from temporalio.service import RPCError, RPCStatusCode

        status = cast(RPCError, error).status
        if status == RPCStatusCode.NOT_FOUND and text.startswith("Namespace"):
            return (
                "Create the namespace (`temporal operator namespace create`) or set "
                "temporal_namespace in --settings."
            )
        if status == RPCStatusCode.NOT_FOUND:
            return (
                "Check the run id and temporal_namespace; `temporal workflow list` shows "
                "existing runs."
            )
        if status in {RPCStatusCode.UNAVAILABLE, RPCStatusCode.DEADLINE_EXCEEDED}:
            return _TEMPORAL_REMEDY
        return None
    if isinstance(error, RuntimeError) and text.startswith("Failed client connect"):
        return _TEMPORAL_REMEDY
    if isinstance(error, TimeoutError):
        return (
            "A service did not answer in time; run `corsair doctor` to check Temporal and Docker."
        )
    if isinstance(error, TargetBindingBlocked) or (
        isinstance(error, ValueError) and text.startswith("agent preview: the workflow stops")
    ):
        return (
            "The case cannot bind its target, so no model would see it; correct finding.line "
            "or the recipe, or run `corsair dataset validate` on its dataset."
        )
    if isinstance(error, ValueError) and text.startswith("agent preview:"):
        return (
            "See `corsair agent preview --help`: the producer takes REQUEST [--round N "
            "--previous FILE --feedback GATE:REASON], the auditor REQUEST --submission FILE."
        )
    if isinstance(error, ValueError) and text.startswith("No committed result"):
        return (
            "Check the run id and artifact_root in --settings; for a run that has not "
            "finished, use `corsair inspect RUN_ID --online`."
        )
    return None
