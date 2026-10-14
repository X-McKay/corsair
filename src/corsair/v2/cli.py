"""Corsair v2 operator CLI.

The module keeps imports intentionally lazy: ``corsair-v2 --help`` and schema
inspection work before optional runtime prerequisites are installed, while each
operation calls its real v2 implementation and never substitutes a fake path.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import ipaddress
import json
import os
import stat
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


class CliError(ValueError):
    """A safe, operator-actionable command refusal."""


_DEPENDENCIES = (
    "PyYAML",
    "openshell",
    "pydantic-ai-slim",
    "pydantic-evals",
    "pydantic-ai-harness",
    "rich",
    "temporalio",
)
_PRIVATE_FILES = 0o600
_PRIVATE_DIRS = 0o700
_MAX_JSON_BYTES = 4 * 1024 * 1024


def _json_default(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Cannot encode {type(value).__name__}")


def _emit(value: Any) -> None:
    """Write structured, non-secret command output to stdout."""
    print(json.dumps(value, default=_json_default, sort_keys=True, ensure_ascii=False, separators=(",", ":")))


def _bounded_regular_file(value: str | Path, *, purpose: str, limit: int = _MAX_JSON_BYTES) -> Path:
    path = Path(value).expanduser().absolute()
    try:
        info = os.lstat(path)
    except OSError as error:
        raise CliError(f"{purpose} must be an existing regular local file") from error
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        raise CliError(f"{purpose} must be a bounded regular non-symlink file")
    return path


def _read_json(value: str | Path, *, purpose: str, limit: int = _MAX_JSON_BYTES) -> dict[str, Any]:
    path = _bounded_regular_file(value, purpose=purpose, limit=limit)
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise CliError(f"{purpose} must contain one UTF-8 JSON object") from error
    if not isinstance(parsed, dict):
        raise CliError(f"{purpose} must contain one JSON object")
    return parsed


def _non_symlink_directory(value: str | Path, *, create: bool = True) -> Path:
    """Return a private local directory, refusing a symlink target."""
    path = Path(value).expanduser().absolute()
    if create:
        try:
            path.mkdir(parents=True, mode=_PRIVATE_DIRS, exist_ok=True)
        except OSError as error:
            raise CliError(f"Cannot create output directory {path}") from error
    try:
        info = os.lstat(path)
    except OSError as error:
        raise CliError(f"Output directory {path} does not exist") from error
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise CliError("Output destination must be a real local directory, not a symlink")
    try:
        os.chmod(path, _PRIVATE_DIRS)
    except OSError as error:
        raise CliError(f"Cannot protect output directory {path}") from error
    return path


def _new_private_file(path: Path, payload: bytes) -> Path:
    """Write one private artifact without replacing a pre-existing path."""
    if path.exists() or path.is_symlink():
        raise CliError(f"Refusing to overwrite existing output {path}")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, _PRIVATE_FILES)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise CliError(f"Refusing to overwrite existing output {path}") from error
    except OSError as error:
        raise CliError(f"Cannot write private output {path}") from error
    return path


def _private_output_directory(value: str | None, *, default_parent: Path, stem: str) -> Path:
    if value:
        return _non_symlink_directory(value)
    root = _non_symlink_directory(default_parent)
    # A random suffix lets an idempotent/cached engine request be exported again
    # without mutating an earlier local copy.
    return _non_symlink_directory(root / f"{stem}-{uuid.uuid4().hex[:12]}")


def _save_native_dataset(dataset: Any, output: str | Path) -> Path:
    """Use the native Dataset serializer while retaining no-overwrite semantics."""
    from corsair.v2.benchmarks import save_dataset

    destination = Path(output).expanduser().absolute()
    parent = _non_symlink_directory(destination.parent)
    if destination.exists() or destination.is_symlink():
        raise CliError(f"Refusing to overwrite existing output {destination}")
    suffix = destination.suffix or ".yaml"
    temporary: Path | None = None
    try:
        descriptor, temp_name = tempfile.mkstemp(prefix=".corsair-v2-dataset-", suffix=suffix, dir=parent)
        os.close(descriptor)
        temporary = Path(temp_name)
        save_dataset(dataset, temporary)
        # link(2) is an atomic no-replace publication within the directory. It
        # also avoids a library writer ever replacing the requested destination.
        os.link(temporary, destination)
        os.chmod(destination, _PRIVATE_FILES)
    except FileExistsError as error:
        raise CliError(f"Refusing to overwrite existing output {destination}") from error
    except OSError as error:
        raise CliError(f"Cannot write native dataset {destination}") from error
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    return destination


def _load_config(path: str):
    from corsair.v2.config import load_config

    return load_config(path)


def _safe_error(error: BaseException, config: Any | None = None) -> str:
    try:
        from corsair.v2.config import safe_error

        return safe_error(error, config)
    except Exception:  # noqa: BLE001 - foreign-library boundary: explicit failed/unknown outcome
        return f"{type(error).__name__}: {str(error)[:1024]}"


def _load_run_spec(path: str):
    from corsair.v2.contracts import RunSpec

    try:
        return RunSpec.model_validate(_read_json(path, purpose="Run specification"))
    except Exception as error:
        raise CliError(_safe_error(error)) from error


def _load_analysis_input(path: str):
    from corsair.v2.contracts import AnalysisInput

    try:
        return AnalysisInput.model_validate(_read_json(path, purpose="Analysis input"))
    except Exception as error:
        raise CliError(_safe_error(error)) from error


def _run_summary(result: Any) -> dict[str, Any]:
    return {
        "schema": "corsair.v2.cli.run-summary.v1",
        "run_id": result.run_id,
        "verdict": result.verdict.status,
        "reason": result.verdict.reason,
        "rule_id": result.verdict.rule_id,
        "qualification": result.qualification,
        "cleanup": result.cleanup,
        "duration_seconds": result.duration_seconds,
        "stage_count": len(result.stages),
        "revision_count": len(result.revisions),
        "evidence_sha256": result.evidence_ref.sha256 if result.evidence_ref else None,
        "report_sha256": result.report_ref.sha256 if result.report_ref else None,
    }


def _result_exit(result: Any) -> int:
    """Do not report an unavailable/unsupported task as CLI success."""
    if result.verdict.status == "unsupported":
        return 3
    if result.verdict.status in {"failed_platform", "cancelled"}:
        return 1
    return 0


def _export_run(result: Any, config: Any, output_dir: str | None) -> dict[str, str]:
    """Copy immutable result/evidence/report bytes into a new private directory."""
    if result.evidence_ref is None or result.report_ref is None:
        raise CliError("Run did not retain both immutable evidence and report artifacts")
    from corsair.v2.contracts import canonical_bytes
    from corsair.v2.storage import Store

    destination = _private_output_directory(
        output_dir,
        default_parent=Path(config.storage_root) / "reports",
        stem=result.run_id,
    )
    store = Store(config.storage_root)
    try:
        evidence = store.get(result.evidence_ref)
        report = store.get(result.report_ref)
    finally:
        store.close()
    result_path = _new_private_file(destination / "result.json", canonical_bytes(result))
    evidence_path = _new_private_file(destination / "evidence.json", evidence)
    report_path = _new_private_file(destination / "report.md", report)
    return {"output_dir": str(destination), "result": str(result_path), "evidence": str(evidence_path), "report": str(report_path)}


async def _direct_run(spec: Any, config: Any) -> Any:
    from corsair.v2.engine import run

    return await run(spec, config)


async def _durable_submit(spec: Any, config: Any, *, wait: bool) -> Any:
    from corsair.v2.temporal import submit

    return await submit(spec, config, wait=wait)


def _cmd_init(args: argparse.Namespace) -> int:
    from corsair.v2.config import write_config
    from corsair.v2.contracts import ModelProfile, OperatorConfig, SandboxProfile

    output = Path(args.output).expanduser().absolute()
    policy = _bounded_regular_file(args.policy, purpose="OpenShell policy", limit=4 * 1024 * 1024)
    gateway = args.gateway.strip()
    if "://" in gateway or "/" in gateway or ":" in gateway:
        raise CliError("--gateway must be an existing native registered gateway name, not a URL or endpoint")
    endpoint = urlsplit(args.base_url)
    if endpoint.query or endpoint.fragment:
        raise CliError("--base-url must not contain a query or fragment; keep credentials only in its environment variable")
    storage_root = Path(args.storage_root).expanduser().absolute()
    try:
        config = OperatorConfig(
            storage_root=str(storage_root),
            default_model=ModelProfile(
                model=args.model,
                provider=args.provider,
                base_url=args.base_url,
                api_key_env=args.api_key_env,
            ),
            sandbox=SandboxProfile(
                image=args.image,
                policy_path=str(policy),
                gateway=gateway,
                workspace=args.workspace,
                workspace_root=args.workspace_root,
            ),
        )
        write_config(output, config)
    except Exception as error:
        raise CliError(_safe_error(error)) from error
    _emit({
        "schema": "corsair.v2.cli.init.v1",
        "config": str(output),
        "storage_root": str(storage_root),
        "model": config.default_model.model,
        "image": config.sandbox.image,
        "gateway": config.sandbox.gateway,
    })
    return 0


def _schema_model(name: str):
    from corsair.v2.contracts import AnalysisInput, OperatorConfig, RunSpec

    models = {
        "operator": OperatorConfig,
        "run": RunSpec,
        "source-analysis": AnalysisInput,
        "sourceanalysis": AnalysisInput,
        "analysis": AnalysisInput,
    }
    return models[name]


def _cmd_schema(args: argparse.Namespace) -> int:
    model = _schema_model(args.schema)
    _emit({"schema": "corsair.v2.cli.schema.v1", "kind": args.schema, "json_schema": model.model_json_schema()})
    return 0


def _dependency_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in _DEPENDENCIES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def _loopback_url(value: str) -> bool:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _profile_health(base_url: str, approved: set[str]) -> dict[str, Any]:
    normalized = base_url.rstrip("/")
    if not _loopback_url(normalized) and normalized not in approved:
        return {"attempted": False, "healthy": None, "reason": "endpoint_not_loopback_or_explicitly_approved"}
    endpoint = normalized + "/models"
    try:
        import httpx
        with httpx.Client(timeout=5, follow_redirects=False) as client, client.stream(
            "GET", endpoint, headers={"Accept": "application/json"}
        ) as response:
            status = response.status_code
        return {"attempted": True, "healthy": 200 <= status < 300, "status": status}
    except Exception as error:  # noqa: BLE001 - foreign-library boundary: explicit failed/unknown outcome
        return {"attempted": True, "healthy": False, "error": f"{type(error).__name__}: {str(error)[:256]}"}


async def _temporal_health(config: Any) -> dict[str, Any]:

    try:
        # Connecting verifies the configured native server/namespace transport;
        # it neither starts a workflow nor submits an activity.
        from corsair.v2.temporal import connect
        await connect(config)
        return {"reachable": True, "address": config.temporal_address, "namespace": config.temporal_namespace}
    except Exception as error:  # noqa: BLE001 - foreign-library boundary: explicit failed/unknown outcome
        return {"reachable": False, "address": config.temporal_address, "namespace": config.temporal_namespace,
                "error": _safe_error(error, config)}


def _cmd_doctor(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    checks: dict[str, Any] = {"dependencies": {"versions": _dependency_versions()}}
    overall = all(value is not None for value in checks["dependencies"]["versions"].values())

    try:
        from corsair.v2.sandbox import Sandbox
        from corsair.v2.storage import Store

        store = Store(config.storage_root)
        try:
            sandbox = Sandbox(config, store)
            health = sandbox.health()
            profile = sandbox.profile_identity()
        finally:
            store.close()
        checks["openshell"] = {"healthy": bool(health.get("gateway_healthy")) and bool(health.get("prerequisites", {}).get("cli_aligned")),
                               "health": health, "profile": profile, "qualified": bool(health.get("qualified"))}
        overall = overall and checks["openshell"]["healthy"]
    except Exception as error:  # noqa: BLE001 - foreign-library boundary: explicit failed/unknown outcome
        checks["openshell"] = {"healthy": False, "error": _safe_error(error, config), "qualified": False}
        overall = False

    temporal = asyncio.run(_temporal_health(config))
    checks["temporal"] = temporal
    overall = overall and temporal["reachable"]

    if args.inference_health:
        approved = {value.rstrip("/") for value in args.approved_base_url}
        profiles = {"default": config.default_model, **config.role_models}
        inference: dict[str, Any] = {}
        for role, profile in profiles.items():
            if profile.provider not in {"openai", "openai-compatible", "ollama"} or not profile.base_url:
                inference[role] = {"attempted": False, "healthy": None, "reason": "no_http_health_endpoint_for_profile"}
                continue
            inference[role] = _profile_health(profile.base_url, approved)
            if inference[role]["attempted"] and inference[role]["healthy"] is False:
                overall = False
        checks["inference"] = inference
    else:
        checks["inference"] = {"attempted": False, "reason": "opt_in_required; no provider request was sent"}

    _emit({"schema": "corsair.v2.cli.doctor.v1", "ok": overall, "checks": checks})
    return 0 if overall else 1


def _cmd_run(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    spec = _load_run_spec(args.spec)
    result = asyncio.run(_durable_submit(spec, config, wait=True) if args.durable else _direct_run(spec, config))
    if not hasattr(result, "verdict"):
        raise CliError("Native Temporal wait did not return a RunResult")
    exported = _export_run(result, config, args.output_dir)
    _emit(_run_summary(result) | {"artifacts": exported, "mode": "durable" if args.durable else "direct"})
    return _result_exit(result)


def _cmd_worker(args: argparse.Namespace) -> int:
    from corsair.v2.temporal import run_worker

    config = _load_config(args.config)
    asyncio.run(run_worker(config))
    return 0


def _cmd_submit(args: argparse.Namespace) -> int:
    config = _load_config(args.config)
    result = asyncio.run(_durable_submit(_load_run_spec(args.spec), config, wait=args.wait))
    if hasattr(result, "verdict"):
        _emit(_run_summary(result) | {"mode": "durable", "waited": True})
        return _result_exit(result)
    _emit({"schema": "corsair.v2.cli.submission.v1", "waited": False, "submission": result})
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    from corsair.v2.temporal import status

    config = _load_config(args.config)
    _emit({"schema": "corsair.v2.cli.status.v1", "status": asyncio.run(status(args.run_id, config))})
    return 0


def _cmd_cancel(args: argparse.Namespace) -> int:
    from corsair.v2.temporal import cancel

    config = _load_config(args.config)
    _emit({"schema": "corsair.v2.cli.cancel.v1", "cancellation": asyncio.run(cancel(args.run_id, config, graceful=args.graceful))})
    return 0


def _cmd_history_export(args: argparse.Namespace) -> int:
    from corsair.v2.temporal import export_history

    config = _load_config(args.config)
    path = asyncio.run(export_history(args.run_id, config, args.output))
    _emit({"schema": "corsair.v2.cli.history-export.v1", "path": str(path), "private": True})
    return 0


def _cmd_history_replay(args: argparse.Namespace) -> int:
    from corsair.v2.temporal import replay

    config = _load_config(args.config)
    history = _bounded_regular_file(args.input, purpose="Temporal history", limit=64 * 1024 * 1024)
    _emit({"schema": "corsair.v2.cli.history-replay.v1", "replay": asyncio.run(replay(history, config))})
    return 0


def _cmd_reconcile(args: argparse.Namespace) -> int:
    from corsair.v2.sandbox import Sandbox
    from corsair.v2.storage import Store

    config = _load_config(args.config)
    store = Store(config.storage_root)
    try:
        result = Sandbox(config, store).reconcile(args.run_id)
    finally:
        store.close()
    _emit({"schema": "corsair.v2.cli.reconcile.v1", "run_id": args.run_id, "observations": result,
           "count": len(result), "note": "persisted ownership is inspected after restart; uncertain effects are never replayed; gateway absence is not driver GC"})
    return 0 if all(row.get("cleanup") == "confirmed" for row in result) else 1


def _cmd_analyze(args: argparse.Namespace) -> int:
    from corsair.v2.runtime import analyze_case

    config = _load_config(args.config)
    result = asyncio.run(analyze_case(_load_analysis_input(args.input), config))
    assessment = result.assessment
    # Keep stdout operational: no captured source and no model rationale are echoed.
    _emit({"schema": "corsair.v2.cli.analysis.v1", "mode": result.mode,
           "prediction": assessment.prediction if assessment else "unknown", "citation_count": len(assessment.citations) if assessment else 0,
           "assessment_available": assessment is not None, "status": result.metrics.status,
           "latency_seconds": result.metrics.latency_seconds, "requests": result.metrics.requests,
           "tool_calls": result.metrics.tool_calls, "input_tokens": result.metrics.input_tokens,
           "output_tokens": result.metrics.output_tokens, "output_sha256": result.output_ref.sha256 if result.output_ref else None})
    return 0 if result.metrics.status == "completed" else 1


def _cmd_benchmark_smoke(args: argparse.Namespace) -> int:
    from corsair.v2.benchmarks import bundled_smoke_dataset

    dataset = bundled_smoke_dataset()
    output = _save_native_dataset(dataset, args.output)
    _emit({"schema": "corsair.v2.cli.dataset.v1", "dataset": str(output), "name": dataset.name,
           "case_count": len(dataset.cases), "mode": "source", "suite_kind": "smoke"})
    return 0


def _dataset_result(dataset: Any, output: str | Path, *, importer: str) -> int:
    path = _save_native_dataset(dataset, output)
    modes = {str(case.metadata.get("input_kind")) for case in dataset.cases}
    _emit({"schema": "corsair.v2.cli.dataset.v1", "dataset": str(path), "name": dataset.name,
           "case_count": len(dataset.cases), "mode": next(iter(modes)) if len(modes) == 1 else "mixed", "importer": importer})
    return 0


def _cmd_import_owasp(args: argparse.Namespace) -> int:
    from corsair.v2.benchmarks import import_owasp

    dataset = import_owasp(
        _bounded_regular_file(args.labels, purpose="OWASP labels"),
        Path(args.source_root).expanduser().absolute(), args.language, args.revision, args.labels_sha256,
        args.suite_name, selected_ids=args.selected_id or None, limit=args.limit,
    )
    return _dataset_result(dataset, args.output, importer="owasp")


def _cmd_import_primevul(args: argparse.Namespace) -> int:
    from corsair.v2.benchmarks import import_primevul

    dataset = import_primevul(_bounded_regular_file(args.input, purpose="PrimeVul JSONL"), args.sha256, args.suite_name,
                              limit=args.limit, license_ref=args.license_ref, snapshot_provenance=args.snapshot_provenance,
                              default_language=args.language, split=args.split)
    return _dataset_result(dataset, args.output, importer="primevul")


def _cmd_import_vul4j(args: argparse.Namespace) -> int:
    from corsair.v2.benchmarks import import_vul4j

    mapping = _read_json(args.repo_mapping, purpose="Vul4J repository mapping")
    source_service = None
    store = None
    if args.source_capture:
        if not args.config:
            raise CliError("--source-capture requires --config so capture uses the real operator Store")
        from corsair.v2.source import SourceService
        from corsair.v2.storage import Store

        config = _load_config(args.config)
        store = Store(config.storage_root)
        source_service = SourceService(store)
    try:
        dataset = import_vul4j(
            _bounded_regular_file(args.csv, purpose="Vul4J CSV"), args.sha256, args.suite_name, args.selected_id,
            repo_mapping=mapping, source_service=source_service, framework_revision=args.framework_revision, split=args.split,
        )
    finally:
        if store is not None:
            store.close()
    return _dataset_result(dataset, args.output, importer="vul4j")


def _evaluation_metadata(dataset_path: Path, mode: str, config: Any) -> dict[str, Any]:
    from corsair.v2.config import config_identity
    from corsair.v2.evaluation import evaluator_policy_identity

    profile = config.model_for("analysis" if mode == "source" else "investigator")
    return {
        "dataset_digest": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "evaluator_policy": evaluator_policy_identity(),
        "execution_profile": "source-analysis-direct" if mode == "source" else "engine-direct",
        "agent": "analysis" if mode == "source" else "investigation",
        "model": profile.model,
        "provider": profile.provider,
        "config_digest": config_identity(config)["config_sha256"],
        "local_telemetry": "logfire-disabled-export",
    }


def _empty_report_targets(output_dir: Path) -> None:
    names = ("evaluation-report.json", "evaluation-records.csv", "evaluation-strata.csv", "evaluation-report.txt")
    existing = [str(output_dir / name) for name in names if (output_dir / name).exists() or (output_dir / name).is_symlink()]
    if existing:
        raise CliError("Refusing to overwrite existing report export(s): " + ", ".join(existing))


def _cmd_eval(args: argparse.Namespace) -> int:
    from corsair.v2.benchmarks import load_dataset
    from corsair.v2.evaluation import evaluate_dataset
    from corsair.v2.reports import export_report

    config = _load_config(args.config)
    dataset_path = _bounded_regular_file(args.dataset, purpose="Native Dataset", limit=64 * 1024 * 1024)
    dataset = load_dataset(dataset_path, args.mode)
    output_dir = _non_symlink_directory(args.output_dir)
    _empty_report_targets(output_dir)
    report = asyncio.run(evaluate_dataset(dataset, config, output_dir, mode=args.mode, repeat=args.repeat,
                                          max_concurrency=args.max_concurrency))
    exported = export_report(report, output_dir, _evaluation_metadata(dataset_path, args.mode, config))
    for path in (exported["report"], exported["records"], exported["strata"], exported["human"]):
        os.chmod(path, _PRIVATE_FILES)
    _emit({"schema": "corsair.v2.cli.evaluation.v1", "mode": args.mode,
           "outputs": {key: value for key, value in exported.items() if key != "summary" and key != "immutable_identity"},
           "summary": exported["summary"]})
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    from corsair.v2.reports import compare_reports

    baseline = _bounded_regular_file(args.baseline, purpose="Baseline report", limit=128 * 1024 * 1024)
    candidate = _bounded_regular_file(args.candidate, purpose="Candidate report", limit=128 * 1024 * 1024)
    output_dir = _non_symlink_directory(args.output_dir)
    for name in ("evaluation-comparison.json", "evaluation-paired.csv"):
        if (output_dir / name).exists() or (output_dir / name).is_symlink():
            raise CliError(f"Refusing to overwrite existing comparison output {output_dir / name}")
    exported = compare_reports(baseline, candidate, output_dir)
    os.chmod(exported["comparison"], _PRIVATE_FILES)
    os.chmod(exported["paired"], _PRIVATE_FILES)
    _emit({"schema": "corsair.v2.cli.comparison.v1", **exported})
    return 0


def _cmd_promote_baseline(args: argparse.Namespace) -> int:
    from corsair.v2.reports import promote_baseline

    report = _bounded_regular_file(args.report, purpose="Evaluation report", limit=128 * 1024 * 1024)
    _emit({"schema": "corsair.v2.cli.baseline-promotion.v1", **promote_baseline(report, Path(args.root))})
    return 0


def _add_config_spec(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", required=True, help="operator-v2 JSON or YAML configuration")
    parser.add_argument("--spec", required=True, help="run-v2 JSON specification")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="corsair-v2", description="Corsair v2 native operator CLI (JSON stdout).")
    parser.add_argument("--version", action="version", version="corsair-v2")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="write a new private operator configuration")
    init.add_argument("--output", required=True)
    init.add_argument("--storage-root", required=True)
    init.add_argument("--model", default="qwen3:4b")
    init.add_argument("--provider", choices=("ollama", "openai", "openai-compatible", "bedrock"), default="ollama")
    init.add_argument("--base-url", default="http://127.0.0.1:11434/v1")
    init.add_argument("--api-key-env", default="OPENAI_API_KEY")
    init.add_argument("--image", required=True, help="OCI image pinned as repository@sha256:<64 hex>")
    init.add_argument("--policy", required=True, help="existing operator-owned OpenShell policy")
    init.add_argument("--gateway", required=True, help="registered native OpenShell gateway name")
    init.add_argument("--workspace", default="default")
    init.add_argument("--workspace-root", default="/workspace")
    init.set_defaults(handler=_cmd_init)

    schema = commands.add_parser("schema", help="emit a v2 JSON Schema")
    schema.add_argument("schema", choices=("operator", "run", "source-analysis", "sourceanalysis", "analysis"), nargs="?", default="operator")
    schema.add_argument("--json", action="store_true", help="explicitly request JSON (the only output format)")
    schema.set_defaults(handler=_cmd_schema)

    doctor = commands.add_parser("doctor", help="check actual local SDK, gateway, profile, and Temporal state")
    doctor.add_argument("--config", required=True)
    doctor.add_argument("--inference-health", action="store_true", help="opt in to read-only GET /models checks")
    doctor.add_argument("--approved-base-url", action="append", default=[], help="non-loopback base URL explicitly approved for GET /models")
    doctor.set_defaults(handler=_cmd_doctor)

    run = commands.add_parser("run", help="run a direct investigation or wait for native Temporal completion")
    _add_config_spec(run)
    run.add_argument("--durable", action="store_true", help="submit to native Temporal and wait for its RunResult")
    run.add_argument("--output-dir", help="private directory for result.json, evidence.json, and report.md")
    run.set_defaults(handler=_cmd_run)

    worker = commands.add_parser("worker", help="run the native Temporal worker until interrupted")
    worker.add_argument("--config", required=True)
    worker.set_defaults(handler=_cmd_worker)

    submit = commands.add_parser("submit", help="submit a durable Temporal investigation")
    _add_config_spec(submit)
    submit.add_argument("--wait", action="store_true", help="wait for the native workflow RunResult")
    submit.set_defaults(handler=_cmd_submit)

    status = commands.add_parser("status", help="query a native Temporal workflow")
    status.add_argument("--config", required=True)
    status.add_argument("--run-id", required=True, help="Temporal workflow id")
    status.set_defaults(handler=_cmd_status)

    cancel = commands.add_parser("cancel", help="cancel or request a graceful stop of a Temporal workflow")
    cancel.add_argument("--config", required=True)
    cancel.add_argument("--run-id", required=True, help="Temporal workflow id")
    cancel.add_argument("--graceful", action="store_true", help="send the native safe-point stop signal")
    cancel.set_defaults(handler=_cmd_cancel)

    history = commands.add_parser("history", help="export or replay native Temporal histories")
    history_commands = history.add_subparsers(dest="history_command", required=True)
    export = history_commands.add_parser("export", help="export one private native workflow history")
    export.add_argument("--config", required=True)
    export.add_argument("--run-id", required=True)
    export.add_argument("--output", required=True)
    export.set_defaults(handler=_cmd_history_export)
    replay = history_commands.add_parser("replay", help="replay a saved native workflow history without effects")
    replay.add_argument("--config", required=True)
    replay.add_argument("--input", required=True)
    replay.set_defaults(handler=_cmd_history_replay)

    reconcile = commands.add_parser("reconcile", help="recover persisted OpenShell ownership and perform only a first identity-checked cleanup")
    reconcile.add_argument("--config", required=True)
    reconcile.add_argument("--run-id")
    reconcile.set_defaults(handler=_cmd_reconcile)

    analyze = commands.add_parser("analyze", help="run source-only AnalysisInput through the native analysis role")
    analyze.add_argument("--config", required=True)
    analyze.add_argument("--input", required=True, help="AnalysisInput JSON")
    analyze.set_defaults(handler=_cmd_analyze)

    benchmark = commands.add_parser("benchmark", help="serialize/import native Pydantic Evals datasets")
    benchmark_commands = benchmark.add_subparsers(dest="benchmark_command", required=True)
    smoke = benchmark_commands.add_parser("smoke", help="serialize the bundled native smoke Dataset")
    smoke.add_argument("--output", required=True)
    smoke.set_defaults(handler=_cmd_benchmark_smoke)

    owasp = benchmark_commands.add_parser("import-owasp", help="import selected pinned OWASP source-only cases")
    owasp.add_argument("--labels", required=True)
    owasp.add_argument("--source-root", required=True)
    owasp.add_argument("--language", required=True, choices=("java", "python"))
    owasp.add_argument("--revision", required=True)
    owasp.add_argument("--labels-sha256", required=True)
    owasp.add_argument("--suite-name", required=True)
    owasp.add_argument("--selected-id", action="append", default=[])
    owasp.add_argument("--limit", type=int)
    owasp.add_argument("--output", required=True)
    owasp.set_defaults(handler=_cmd_import_owasp)

    primevul = benchmark_commands.add_parser("import-primevul", help="import a pinned PrimeVul source-only snapshot")
    primevul.add_argument("--input", required=True)
    primevul.add_argument("--sha256", required=True)
    primevul.add_argument("--suite-name", required=True)
    primevul.add_argument("--license-ref", "--license", dest="license_ref", required=True, help="license retained for this exact snapshot")
    primevul.add_argument("--snapshot-provenance", "--label-provenance", dest="snapshot_provenance", required=True, help="verified provenance for this exact snapshot")
    primevul.add_argument("--language", default="C/C++", help="explicit language for canonical upstream rows, which have no lang field")
    primevul.add_argument("--split", default="public-dev")
    primevul.add_argument("--limit", type=int)
    primevul.add_argument("--output", required=True)
    primevul.set_defaults(handler=_cmd_import_primevul)

    vul4j = benchmark_commands.add_parser("import-vul4j", help="import selected paired Vul4J cases")
    vul4j.add_argument("--csv", required=True)
    vul4j.add_argument("--sha256", required=True)
    vul4j.add_argument("--suite-name", required=True)
    vul4j.add_argument("--selected-id", action="append", required=True)
    vul4j.add_argument("--repo-mapping", required=True, help="JSON mapping of already-acquired pinned local repositories")
    vul4j.add_argument("--framework-revision")
    vul4j.add_argument("--split", default="public-dev")
    vul4j.add_argument("--config", help="required with --source-capture")
    vul4j.add_argument("--source-capture", action="store_true", help="capture mapped commits through real SourceService")
    vul4j.add_argument("--output", required=True)
    vul4j.set_defaults(handler=_cmd_import_vul4j)

    evaluation = commands.add_parser("eval", help="run a native Dataset evaluation and export complete-denominator reports")
    evaluation.add_argument("--dataset", required=True)
    evaluation.add_argument("--mode", required=True, choices=("source", "run"))
    evaluation.add_argument("--repeat", type=int, default=1)
    evaluation.add_argument("--max-concurrency", type=int, default=1)
    evaluation.add_argument("--output-dir", required=True)
    evaluation.add_argument("--config", required=True)
    evaluation.set_defaults(handler=_cmd_eval)

    compare = commands.add_parser("compare", help="compare compatible exported evaluation reports")
    compare.add_argument("--baseline", required=True)
    compare.add_argument("--candidate", required=True)
    compare.add_argument("--output-dir", required=True)
    compare.set_defaults(handler=_cmd_compare)

    promote = commands.add_parser("promote-baseline", help="create a digest-addressed non-smoke baseline reference")
    promote.add_argument("--report", required=True)
    promote.add_argument("--root", required=True)
    promote.set_defaults(handler=_cmd_promote_baseline)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one explicit v2 command and return a shell-compatible status."""
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        return int(args.handler(args))
    except SystemExit as error:
        # argparse owns standard --help/usage rendering.  Returning its status
        # keeps this callable entry point convenient for tests and v1 dispatch.
        return int(error.code) if isinstance(error.code, int) else 1
    except CliError as error:
        print(f"corsair-v2: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("corsair-v2: interrupted", file=sys.stderr)
        return 130
    except Exception as error:  # noqa: BLE001 - foreign-library boundary: explicit failed/unknown outcome
        # Config-aware redaction is used inside handlers once a config exists;
        # this last-resort boundary deliberately avoids traceback/prompt output.
        print(f"corsair-v2: {_safe_error(error)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
