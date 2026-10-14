"""Native Pydantic Evals benchmark datasets for Corsair v2.

Labels are deliberately kept in ``Case.expected_output`` and metadata.  The
case input is the only value passed to a task, so no importer puts a label,
CVE, test id, or expected disposition in agent-visible source context.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import tokenize
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic_evals import Case, Dataset

from .contracts import AnalysisInput, RunSpec, SourceRequest, digest

_MAX_SOURCE_BYTES = 256 * 1024
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")


class BenchmarkImportError(ValueError):
    """A public dataset row could not be admitted without changing its meaning."""


def _sha256_file(path: Path, expected: str) -> None:
    if not _SHA256.fullmatch(expected):
        raise BenchmarkImportError("A lowercase SHA-256 digest is required")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise BenchmarkImportError(f"SHA-256 mismatch for {path}: expected {expected}, got {actual}")


def _require_text(path: Path) -> str:
    data = path.read_bytes()
    if len(data) > _MAX_SOURCE_BYTES:
        raise BenchmarkImportError(f"Source file exceeds the 256 KiB benchmark input limit: {path}")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise BenchmarkImportError(f"Source file is not UTF-8: {path}") from error


def _extension(language: str) -> str:
    return {"python": "py", "java": "java", "javascript": "js", "c": "c", "c++": "cpp", "c/c++": "c"}.get(
        language.lower(), "txt"
    )


def _neutral_path(source: str, language: str) -> str:
    """Give a public source slice a deterministic, non-label-bearing filename."""
    return f"source/{hashlib.sha256(source.encode()).hexdigest()[:24]}.{_extension(language)}"


def _strip_python_comments(text: str) -> str:
    """Remove comments and pytest/unittest decorator headers while preserving code strings.

    The transform is intentionally source-only: it does not claim that the
    result compiles.  The raw path and raw SHA-256 remain in case provenance.
    """
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError) as error:
        raise BenchmarkImportError("Python source cannot be tokenized for label-hygiene transform") from error
    kept: list[tokenize.TokenInfo] = []
    for token in tokens:
        if token.type == tokenize.COMMENT:
            continue
        kept.append(token)
    result = tokenize.untokenize(kept)
    return "\n".join(
        line for line in result.splitlines()
        if not re.match(r"^\s*@(?:pytest\.|unittest\.)?(?:mark\.|skip|xfail|parameterized|test)", line)
    ) + ("\n" if result.endswith("\n") else "")


def _strip_c_style_comments(text: str) -> str:
    """Remove // and /* */ comments without treating comment delimiters in strings as comments."""
    out: list[str] = []
    index, state = 0, "code"
    while index < len(text):
        char = text[index]
        following = text[index + 1] if index + 1 < len(text) else ""
        if state == "code" and char == '"':
            state = "double"
            out.append(char)
        elif state == "code" and char == "'":
            state = "single"
            out.append(char)
        elif state == "code" and char == "/" and following == "/":
            state = "line"
            index += 1
        elif state == "code" and char == "/" and following == "*":
            state = "block"
            index += 1
        elif state == "line":
            if char == "\n":
                state = "code"
                out.append(char)
        elif state == "block":
            if char == "*" and following == "/":
                state = "code"
                index += 1
            elif char == "\n":
                out.append(char)
        else:
            out.append(char)
            if char == "\\" and index + 1 < len(text):
                index += 1
                out.append(text[index])
            elif (state == "double" and char == '"') or (state == "single" and char == "'"):
                state = "code"
        index += 1
    if state == "block":
        raise BenchmarkImportError("Unterminated block comment in source transform")
    return "\n".join(
        line for line in "".join(out).splitlines()
        if not re.match(r"^\s*@(?:Test|ParameterizedTest|RepeatedTest)\b", line)
    ) + ("\n" if text.endswith("\n") else "")


def _sanitize_source(text: str, language: str) -> str:
    """Documented OWASP source-only hygiene transform, version 1.

    * remove all lexical comments (not text in string literals);
    * remove recognizable test/decorator headers; and
    * retain the executable source lines unchanged.

    This removes the common OWASP label-bearing explanatory comments and makes
    the input filename neutral.  ``raw_path`` and ``raw_sha256`` are retained
    only in evaluator metadata/provenance, never in ``AnalysisInput``.
    """
    value = _strip_python_comments(text) if language.lower() == "python" else _strip_c_style_comments(text)
    if not value.strip():
        raise BenchmarkImportError("Label-hygiene transform left no source code")
    if len(value.encode()) > _MAX_SOURCE_BYTES:
        raise BenchmarkImportError("Sanitized source exceeds the 256 KiB benchmark input limit")
    return value


def _case_metadata(*, suite: str, suite_kind: str, language: str, framework: str, cwe: Iterable[str],
                   split: str, source_digest: str, provenance: Mapping[str, Any], task_mode: str = "source",
                   promotion_eligible: bool = True, not_comparable_to_upstream: bool = False,
                   generated: bool = False, **extra: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "schema": "corsair.benchmark-metadata.v2",
        "suite_id": suite,
        "suite_kind": suite_kind,
        "task_mode": task_mode,
        "language": language,
        "framework": framework,
        "cwe": list(cwe),
        "split": split,
        "source_digest": source_digest,
        "provenance": dict(provenance),
        "promotion_eligible": promotion_eligible,
        "not_comparable_to_upstream": not_comparable_to_upstream,
        "generated": generated,
        "expected_label_status": "sealed",
    }
    value.update(extra)
    return value


def _typed_dataset(name: str, cases: list[Case[Any, str, dict[str, Any]]], *, mode: str) -> Dataset:
    if not cases:
        raise BenchmarkImportError("Dataset import produced no cases")
    # Generic specialization documents the native runner contract and makes
    # Dataset.to_file() serialize model inputs rather than a private schema.
    if mode == "source":
        return Dataset[AnalysisInput, str, dict[str, Any]](name=name, cases=cases)
    if mode == "run":
        return Dataset[RunSpec, str, dict[str, Any]](name=name, cases=cases)
    raise BenchmarkImportError("mode must be 'source' or 'run'")


def _retype_native_dataset(dataset: Dataset, mode: str) -> Dataset:
    cases: list[Case[Any, str, dict[str, Any]]] = []
    for raw in dataset.cases:
        metadata = dict(raw.metadata or {})
        kind = metadata.get("input_kind", mode)
        if kind not in ("source", "run"):
            raise BenchmarkImportError("Native dataset metadata input_kind must be 'source' or 'run'")
        try:
            inputs = AnalysisInput.model_validate(raw.inputs) if kind == "source" else RunSpec.model_validate(raw.inputs)
        except Exception as error:
            raise BenchmarkImportError(f"Native dataset case {raw.name!r} has invalid {kind} inputs") from error
        if not isinstance(raw.expected_output, str):
            raise BenchmarkImportError(f"Native dataset case {raw.name!r} requires a string expected_output")
        metadata["input_kind"] = kind
        cases.append(Case(name=raw.name, inputs=inputs, metadata=metadata, expected_output=raw.expected_output,
                          evaluators=raw.evaluators))
    modes = {case.metadata["input_kind"] for case in cases}
    if len(modes) != 1 or mode not in modes:
        raise BenchmarkImportError(f"Native dataset mode is {modes!r}, not requested {mode!r}")
    return _typed_dataset(dataset.name, cases, mode=mode)


def load_dataset(path: Path, mode: str = "source") -> Dataset:
    """Load a normal Pydantic Evals YAML/JSON Dataset and restore typed inputs.

    This intentionally accepts only the native Dataset serialization, not a
    second Corsair YAML format.  The input type is selected by explicit mode
    and recorded ``metadata.input_kind`` so an accidental source/run mismatch
    is rejected rather than silently coerced.
    """
    if mode not in ("source", "run"):
        raise BenchmarkImportError("mode must be 'source' or 'run'")
    suffix = path.suffix.lower()
    if suffix not in (".yaml", ".yml", ".json"):
        raise BenchmarkImportError("Dataset path must end in .yaml, .yml, or .json")
    try:
        dataset_type = Dataset[AnalysisInput, str, dict[str, Any]] if mode == "source" else Dataset[RunSpec, str, dict[str, Any]]
        native = dataset_type.from_file(path, fmt="json" if suffix == ".json" else "yaml")
    except Exception as error:
        raise BenchmarkImportError(f"Cannot load native Dataset {path}") from error
    return _retype_native_dataset(native, mode)


def save_dataset(dataset: Dataset, path: Path) -> Path:
    """Persist a native Dataset serialization without emitting a sidecar schema."""
    path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_file(path, schema_path=None)
    return path


def _owasp_labels(labels: Path) -> list[tuple[str, str, bool, str]]:
    rows: list[tuple[str, str, bool, str]] = []
    seen: set[str] = set()
    text = labels.read_text(encoding="utf-8")
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        row = next(csv.reader([line], strict=True), None)
        if row is None or len(row) != 4:
            raise BenchmarkImportError(f"OWASP labels line {line_number} is not an exact four-column row")
        test_id, category, truth, cwe = (field.strip() for field in row)
        if not re.fullmatch(r"BenchmarkTest\d+", test_id) or not category or truth not in ("true", "false") or not cwe.isdigit():
            raise BenchmarkImportError(f"OWASP labels line {line_number} violates the pinned positional format")
        if test_id in seen:
            raise BenchmarkImportError(f"Duplicate OWASP test id {test_id}")
        seen.add(test_id)
        rows.append((test_id, category, truth == "true", f"CWE-{int(cwe)}"))
    if not rows:
        raise BenchmarkImportError("OWASP labels contain no data rows")
    return rows


def _exact_source_index(source_root: Path, language: str) -> dict[str, list[Path]]:
    extension = "." + _extension(language)
    index: dict[str, list[Path]] = {}
    for path in source_root.rglob(f"*{extension}"):
        if path.is_file() and not path.is_symlink() and re.fullmatch(r"BenchmarkTest\d+", path.stem):
            index.setdefault(path.stem, []).append(path)
    return index


def import_owasp(labels: Path, source_root: Path, language: str, revision: str, labels_sha256: str,
                 suite_name: str, selected_ids: list[str] | None = None, limit: int | None = None) -> Dataset:
    """Import exact OWASP four-column labels as source-only native cases.

    ``source_root`` must already be an immutable local checkout/capture of the
    exact supplied commit.  Matching is exact file-stem equality, never a
    substring gate; all selected labels must resolve to exactly one file.
    """
    if language not in ("java", "python"):
        raise BenchmarkImportError("OWASP importer currently supports exact Java or Python source files")
    if not _GIT_SHA.fullmatch(revision):
        raise BenchmarkImportError("OWASP revision must be an exact 40-character commit")
    if not source_root.is_dir() or source_root.is_symlink():
        raise BenchmarkImportError("source_root must be an existing non-symlink directory")
    _sha256_file(labels, labels_sha256)
    rows = _owasp_labels(labels)
    by_id = {row[0]: row for row in rows}
    if selected_ids is not None:
        if len(selected_ids) != len(set(selected_ids)):
            raise BenchmarkImportError("selected_ids contains duplicates")
        missing = [value for value in selected_ids if value not in by_id]
        if missing:
            raise BenchmarkImportError(f"Selected OWASP labels are missing: {missing}")
        rows = [by_id[value] for value in selected_ids]
    if limit is not None:
        if not isinstance(limit, int) or limit < 1:
            raise BenchmarkImportError("limit must be a positive integer")
        rows = rows[:limit]
    index = _exact_source_index(source_root, language)
    cases: list[Case[Any, str, dict[str, Any]]] = []
    for test_id, category, vulnerable, cwe in rows:
        matches = index.get(test_id, [])
        if len(matches) != 1:
            raise BenchmarkImportError(f"OWASP {test_id} must resolve to exactly one {language} source file, got {len(matches)}")
        raw_path = matches[0]
        raw = _require_text(raw_path)
        source = _sanitize_source(raw, language)
        source_digest = hashlib.sha256(source.encode()).hexdigest()
        public_input = AnalysisInput(files={_neutral_path(source, language): source}, language=language,
                                     framework="unknown")
        expected = "vulnerable" if vulnerable else "safe_in_scope"
        metadata = _case_metadata(
            suite=suite_name, suite_kind="upstream", language=language, framework="unknown", cwe=(cwe,),
            split="public-dev", source_digest=source_digest,
            provenance={"dataset": "OWASP Benchmark", "revision": revision, "labels_sha256": labels_sha256,
                        "license": "GPL-2.0" if language == "java" else "GPL-3.0",
                        "raw_path": str(raw_path.relative_to(source_root)),
                        "raw_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                        "source_transform": "corsair-owasp-comment-and-test-header-strip-v1"},
            label_quality="synthetic_author_label", ground_truth={"target_state": "vulnerable" if vulnerable else "not_vulnerable",
                                                                    "category": category}, input_kind="source",
        )
        cases.append(Case(name=f"{suite_name}/{test_id}", inputs=public_input, expected_output=expected, metadata=metadata))
    return _typed_dataset(suite_name, cases, mode="source")


def import_primevul(jsonl: Path, sha256: str, suite_name: str, limit: int | None = None, *,
                    default_language: str = "C/C++", license_ref: str | None = None,
                    snapshot_provenance: str | None = None, split: str = "public-dev",
                    license: str | None = None, label_provenance: str | None = None) -> Dataset:
    """Import a pinned PrimeVul JSONL snapshot as source classification data.

    Actual PrimeVul function rows use ``func``, ``target``, ``project``, and
    ``commit_id``; they do not carry a language field.  Canonical rows therefore
    use the explicit caller-controlled ``default_language`` (``C/C++`` by
    default) and never infer a CWE.  The former normalized row shape with
    ``lang`` and ``commit`` remains accepted for already captured local data.

    The data artifact is not licensed merely because the PrimeVul code repository
    has a license.  A caller must retain a concrete ``license_ref`` and
    ``snapshot_provenance`` with the pinned file.  ``license`` and
    ``label_provenance`` are compatibility aliases for existing callers; neither
    has an automatic default.
    """
    if license_ref and license and license_ref != license:
        raise BenchmarkImportError("PrimeVul license_ref conflicts with legacy license")
    if snapshot_provenance and label_provenance and snapshot_provenance != label_provenance:
        raise BenchmarkImportError("PrimeVul snapshot_provenance conflicts with legacy label_provenance")
    license_ref = license_ref or license
    snapshot_provenance = snapshot_provenance or label_provenance
    if not isinstance(default_language, str) or not default_language.strip():
        raise BenchmarkImportError("PrimeVul default_language must be a nonempty caller-supplied language")
    has_snapshot_provenance = (
        isinstance(license_ref, str) and bool(license_ref.strip())
        and isinstance(snapshot_provenance, str) and bool(snapshot_provenance.strip())
    )
    if not has_snapshot_provenance:
        raise BenchmarkImportError(
            "PrimeVul requires caller-supplied license_ref and snapshot_provenance for the pinned snapshot"
        )
    _sha256_file(jsonl, sha256)
    if limit is not None and (not isinstance(limit, int) or limit < 1):
        raise BenchmarkImportError("limit must be a positive integer")
    cases: list[Case[Any, str, dict[str, Any]]] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(jsonl.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip():
            raise BenchmarkImportError(f"PrimeVul JSONL has an empty row at {line_number}")
        try:
            row = json.loads(raw_line)
        except json.JSONDecodeError as error:
            raise BenchmarkImportError(f"PrimeVul JSONL row {line_number} is invalid") from error
        if not isinstance(row, dict):
            raise BenchmarkImportError(f"PrimeVul JSONL row {line_number} must be an object")
        canonical = all(key in row for key in ("func", "target", "project", "commit_id"))
        normalized = all(key in row for key in ("func", "target", "lang", "project", "commit"))
        if not canonical and not normalized:
            raise BenchmarkImportError(
                f"PrimeVul JSONL row {line_number} lacks canonical func/target/project/commit_id "
                "or legacy normalized func/target/lang/project/commit keys"
            )
        if canonical:
            func, target, project, commit = (row[key] for key in ("func", "target", "project", "commit_id"))
            language = default_language
            commit_field = "commit_id"
        else:
            func, target, lang, project, commit = (row[key] for key in ("func", "target", "lang", "project", "commit"))
            language = lang.lower() if isinstance(lang, str) else lang
            commit_field = "commit"
        valid_values = all(isinstance(value, str) for value in (func, project, commit, language))
        if not valid_values or target not in (0, 1, "0", "1"):
            raise BenchmarkImportError(f"PrimeVul JSONL row {line_number} has invalid label or canonical key values")
        within_bounds = (
            func.strip() and len(func.encode()) <= _MAX_SOURCE_BYTES and project.strip() and language.strip()
            and _GIT_SHA.fullmatch(commit)
        )
        if not within_bounds:
            raise BenchmarkImportError(
                f"PrimeVul JSONL row {line_number} exceeds bounds or lacks an immutable commit_id"
            )
        source_digest = hashlib.sha256(func.encode()).hexdigest()
        case_id = f"{suite_name}/{project}/{commit}/{source_digest[:16]}"
        if case_id in seen:
            raise BenchmarkImportError(f"Duplicate PrimeVul case identity {case_id}")
        seen.add(case_id)
        expected = "vulnerable" if str(target) == "1" else "safe_in_scope"
        metadata = _case_metadata(
            suite=suite_name, suite_kind="upstream", language=language, framework="unknown", cwe=(), split=split,
            source_digest=source_digest,
            provenance={"dataset": "PrimeVul", "data_sha256": sha256, "license_ref": license_ref,
                        "snapshot_provenance": snapshot_provenance, "project": project, commit_field: commit},
            label_quality=snapshot_provenance,
            ground_truth={"target_state": "vulnerable" if expected == "vulnerable" else "not_vulnerable"},
            input_kind="source",
        )
        inputs = AnalysisInput(files={_neutral_path(func, language): func}, language=language, framework="unknown")
        cases.append(Case(name=case_id, inputs=inputs, expected_output=expected, metadata=metadata))
        if limit is not None and len(cases) >= limit:
            break
    return _typed_dataset(suite_name, cases, mode="source")


def _patch_commit(url: str) -> str:
    parsed = urlparse(url)
    candidate = parsed.path.rstrip("/").split("/")[-1]
    if not _GIT_SHA.fullmatch(candidate):
        raise BenchmarkImportError("Vul4J human_patch must end in an immutable 40-character commit")
    return candidate


def import_vul4j(csv_path: Path, sha256: str, suite_name: str, selected_ids: list[str], *,
                 repo_mapping: Mapping[str, Mapping[str, str]], source_service: Any | None = None,
                 framework_revision: str | None = None, split: str = "public-dev") -> Dataset:
    """Import selected Vul4J rows as full-system paired ``RunSpec`` cases.

    ``repo_mapping`` is an explicit already-acquired/pinned local mapping:
    ``{repo_slug: {"path": "/absolute/repo", "baseline_commit": sha,
    "candidate_commit": sha}}``.  It is required because an importer must not
    use dataset shell commands.  If ``source_service`` is supplied, both commits
    are captured through the trusted ``SourceService`` before cases are emitted.
    """
    _sha256_file(csv_path, sha256)
    if not selected_ids or len(selected_ids) != len(set(selected_ids)):
        raise BenchmarkImportError("selected_ids must be a nonempty duplicate-free explicit Vul4J subset")
    if framework_revision is not None and not _GIT_SHA.fullmatch(framework_revision):
        raise BenchmarkImportError("framework_revision must be an exact 40-character commit")
    with csv_path.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    expected_headers = {"vul_id", "cwe_id", "repo_slug", "human_patch", "build_system", "failing_tests"}
    if not rows or not expected_headers.issubset(rows[0]):
        raise BenchmarkImportError("Vul4J CSV is missing required quoted-CSV headers")
    by_id = {row.get("vul_id", ""): row for row in rows}
    if len(by_id) != len(rows):
        raise BenchmarkImportError("Vul4J CSV has duplicate or blank vul_id rows")
    missing = [case_id for case_id in selected_ids if case_id not in by_id]
    if missing:
        raise BenchmarkImportError(f"Selected Vul4J IDs are absent: {missing}")
    cases: list[Case[Any, str, dict[str, Any]]] = []
    for case_id in selected_ids:
        row = by_id[case_id]
        repo_slug = row["repo_slug"].strip()
        mapping = repo_mapping.get(repo_slug)
        if not mapping:
            raise BenchmarkImportError(f"Vul4J {case_id} lacks an already-acquired repo_mapping for {repo_slug}")
        path, baseline, candidate = mapping.get("path"), mapping.get("baseline_commit"), mapping.get("candidate_commit")
        patch = _patch_commit(row["human_patch"].strip())
        if not isinstance(path, str) or not path or not isinstance(baseline, str) or not isinstance(candidate, str):
            raise BenchmarkImportError(f"Vul4J {case_id} repo_mapping requires path, baseline_commit, and candidate_commit")
        if not _GIT_SHA.fullmatch(baseline) or not _GIT_SHA.fullmatch(candidate) or candidate != patch:
            raise BenchmarkImportError(f"Vul4J {case_id} mapping must pin the human patch and exact baseline commit")
        local = Path(path)
        if not local.is_absolute() or not local.is_dir() or local.is_symlink():
            raise BenchmarkImportError(f"Vul4J {case_id} mapping path must be an absolute non-symlink local repository")
        if source_service is not None:
            # SourceService owns safe native Git capture; this is not an unchecked
            # raw dataset command.  The snapshots also prove these exact commits exist.
            source_service.capture(SourceRequest(path=str(local), commit=baseline))
            source_service.capture(SourceRequest(path=str(local), commit=baseline, candidate_path=str(local),
                                                 candidate_commit=candidate), revision="candidate")
        cwe = row["cwe_id"].strip()
        if not re.fullmatch(r"CWE-\d+", cwe):
            raise BenchmarkImportError(f"Vul4J {case_id} has invalid cwe_id")
        spec = RunSpec(request_id=f"eval-{hashlib.sha256((suite_name + case_id).encode()).hexdigest()[:32]}",
                       source=SourceRequest(path=str(local), commit=baseline, candidate_path=str(local),
                                            candidate_commit=candidate),
                       concern=f"Evaluate the scoped vulnerability represented by {case_id}.", language="java",
                       framework=row["build_system"].strip() or "unknown", cwe=(cwe,))
        source_digest = digest({"repo_slug": repo_slug, "baseline": baseline, "candidate": candidate})
        metadata = _case_metadata(
            suite=suite_name, suite_kind="upstream", language="java", framework=spec.framework, cwe=(cwe,), split=split,
            source_digest=source_digest, task_mode="run",
            provenance={"dataset": "Vul4J", "dataset_sha256": sha256, "dataset_license": "CC-BY-4.0",
                        "repository": repo_slug, "baseline_commit": baseline, "candidate_commit": candidate,
                        "framework_revision": framework_revision, "human_patch": row["human_patch"]},
            label_quality="human_patch_pov", ground_truth={"target_state": "vulnerable_fixed_pair"},
            controls_required=True, input_kind="run", failing_tests=row["failing_tests"],
        )
        cases.append(Case(name=f"{suite_name}/{case_id}", inputs=spec, expected_output="verified_repair", metadata=metadata))
    return _typed_dataset(suite_name, cases, mode="run")


def bundled_smoke_dataset() -> Dataset:
    """Load the original Apache-2.0 native smoke YAML shipped with this package."""
    return load_dataset(Path(__file__).with_name("data") / "corsair-smoke-v1.yaml", mode="source")
