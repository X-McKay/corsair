"""Frozen two-probe execution. Formats select parsers, never security verdicts."""
from __future__ import annotations

import json
import re
from collections.abc import Callable

from corsair.ports.test_runner import RubyTestId
from corsair.reports.jest import parse_jest
from corsair.reports.junit import admit_xml
from corsair.reports.minitest import parse_minitest

from .contracts import (
    CommandResult,
    InvestigationPlan,
    OperatorConfig,
    ProbeObservation,
    RevisionExecution,
    SourceSnapshot,
    digest,
)
from .sandbox import Sandbox, SandboxBoundaryError
from .storage import Store

_MAX_REPORT_BYTES = 256 * 1024
_ASSERTION_TYPES = {"AssertionError", "AssertionFailedError", "AssertionException", "AssertionFailure", "AssertError"}
_JEST_OUTCOMES = {"passed": "passed", "failed": "failed", "pending": "skipped", "skipped": "skipped",
                  "todo": "skipped", "disabled": "skipped"}
_TAP_SUBTEST = re.compile(r"# Subtest: (?P<name>.+)")
_TAP_RESULT = re.compile(r"(?P<not>not )?ok (?P<number>[1-9]\d*)(?: - (?P<name>.*?))?"
                         r"(?:\s+#\s*(?P<directive>skip|todo)\b.*)?\s*", re.IGNORECASE)
_TAP_PLAN = re.compile(r"1\.\.(?P<count>\d+)\s*")


class _NativeCancellation(Exception):
    """A cooperative cancellation observed before dispatching the next command."""


def _assertion(type_name: str, body: str) -> bool:
    # A JUnit <failure> is not necessarily an assertion: pytest puts ValueError
    # inside <failure>, too. Never relabel arbitrary runtime errors as exploits.
    if type_name.rsplit(".", 1)[-1] in _ASSERTION_TYPES:
        return True
    return bool(re.search(r"(?:^|\n)(?:E\s+)?(?:[\w.]*\.)?AssertionError(?::|\s|$)", body))


def _document(report: bytes, what: str) -> dict:
    """Read one bounded JSON document, refusing duplicate object keys."""
    if type(report) is not bytes or not report or len(report) > _MAX_REPORT_BYTES:
        raise ValueError(f"{what} report is outside the admitted byte envelope")

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"Duplicate key in {what} report")
            value[key] = item
        return value

    try:
        value = json.loads(report.decode("utf-8"), object_pairs_hook=unique)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise ValueError(f"Invalid {what} report: {type(error).__name__}") from error
    if type(value) is not dict:
        raise ValueError(f"Expected a {what} JSON object")
    return value


def _repo_rel(value: object, root: str, path: str) -> bool:
    """An actual suite path must equal, not merely suffix-match, its frozen path."""
    return type(value) is str and value in (path, root.rstrip("/") + "/" + path)


def _junit(report: bytes, plan: InvestigationPlan) -> tuple[ProbeObservation, ...]:
    tree = admit_xml(report, _MAX_REPORT_BYTES)
    if tree.tag not in ("testsuite", "testsuites"):
        raise ValueError("Unexpected JUnit root")
    probes = (plan.control, plan.security)
    keys = {(p.selector.classname, p.selector.name): p.test_id for p in probes}
    if len(keys) != 2:
        raise ValueError("JUnit selectors are ambiguous")
    found = {}
    for case in tree.iter("testcase"):
        identity = keys.get((case.get("classname", ""), case.get("name", "")))
        if identity is None or identity in found:
            raise ValueError("Unexpected or duplicate native testcase")
        allowed = {"failure", "error", "skipped", "system-out", "system-err", "properties"}
        if any(child.tag not in allowed for child in case):
            raise ValueError("Unexpected testcase child")
        marks = [child for child in case if child.tag in ("failure", "error", "skipped")]
        if len(marks) > 1:
            raise ValueError("Ambiguous native testcase outcome")
        outcome, failure_type, detail = "passed", None, ""
        if marks:
            mark = marks[0]
            outcome = {"failure": "failed", "error": "error", "skipped": "skipped"}[mark.tag]
            body = mark.text or ""
            detail = ((mark.get("message") or "") + "\n" + body)[:2048]
            if outcome == "failed":
                failure_type = "assertion" if _assertion(mark.get("type", ""), body) else (mark.get("type") or "other")
        found[identity] = ProbeObservation(test_id=identity, outcome=outcome, failure_type=failure_type, detail=detail)
    if set(found) != {p.test_id for p in probes}:
        raise ValueError("Both native testcase records are required")
    return tuple(found[p.test_id] for p in probes)


def _jest_entries(report: bytes, plan: InvestigationPlan, root: str, *, listing: bool) -> tuple[tuple[object, str, tuple[str, ...], dict], ...]:
    """Normalize a real aggregated Jest report across the two independent files."""
    document = _document(report, "Jest")
    suites = document.get("testResults")
    if type(suites) is not list or type(document.get("numRuntimeErrorTestSuites")) is not int \
            or document["numRuntimeErrorTestSuites"] != 0:
        raise ValueError("Expected Jest suites without runtime errors")
    probes = (plan.control, plan.security)
    selectors = {(probe.path, probe.selector.classname, probe.selector.name): probe for probe in probes}
    if len(selectors) != 2:
        raise ValueError("Jest selectors are ambiguous")
    entries: dict[str, tuple[object, str, tuple[str, ...], dict]] = {}
    for suite in suites:
        if type(suite) is not dict or type(suite.get("name")) is not str or type(suite.get("assertionResults")) is not list:
            raise ValueError("Malformed Jest suite")
        if suite.get("message") not in (None, "") or suite.get("testExecError") is not None:
            raise ValueError("Jest suite reported an execution error")
        paths = [probe.path for probe in probes if _repo_rel(suite["name"], root, probe.path)]
        if len(paths) != 1:
            raise ValueError("Unexpected Jest suite path")
        for test in suite["assertionResults"]:
            if (type(test) is not dict or type(test.get("title")) is not str or type(test.get("ancestorTitles")) is not list
                    or any(type(title) is not str for title in test["ancestorTitles"]) or type(test.get("status")) is not str
                    or test["status"] not in _JEST_OUTCOMES or type(test.get("failureMessages")) is not list
                    or any(type(message) is not str for message in test["failureMessages"])):
                raise ValueError("Malformed Jest assertion result")
            probe = selectors.get((paths[0], "::".join(test["ancestorTitles"]), test["title"]))
            if probe is None or probe.test_id in entries:
                raise ValueError("Unexpected or duplicate Jest testcase")
            status, messages = test["status"], tuple(test["failureMessages"])
            if listing:
                if status != "pending" or messages:
                    raise ValueError("Jest discovery executed or omitted a testcase")
            elif (_JEST_OUTCOMES[status] == "failed") != bool(messages):
                raise ValueError("Jest outcome and failure messages disagree")
            entries[probe.test_id] = (probe, status, messages, suite)
    expected = {probe.test_id for probe in probes}
    if set(entries) != expected:
        raise ValueError("Both native Jest testcase records are required")
    return tuple(entries[probe.test_id] for probe in probes)


def _jest(report: bytes, plan: InvestigationPlan, root: str) -> tuple[ProbeObservation, ...]:
    values = []
    for probe, status, messages, suite in _jest_entries(report, plan, root, listing=False):
        # The legacy parser remains authoritative where its one-suite/id grammar
        # fits. Selector/path normalization above is what admits a two-file plan.
        legacy = None
        try:
            legacy = parse_jest(json.dumps({"testResults": [suite], "numRuntimeErrorTestSuites": 0}).encode(),
                                (probe.test_id,), root=root, test_paths=frozenset((probe.path,)), max_bytes=_MAX_REPORT_BYTES)[0]
        except ValueError:
            pass
        outcome = _JEST_OUTCOMES[status]
        if legacy is not None and legacy.outcome != outcome:
            raise ValueError("Jest legacy and normalized outcomes disagree")
        detail = (legacy.failure.message if legacy and legacy.failure else "\n".join(messages))[:2048]
        failure_type = None
        if outcome == "failed":
            error_type = legacy.failure.type if legacy and legacy.failure else ""
            failure_type = "assertion" if (_assertion(error_type or "", detail) or bool(re.search(r"expect\(.+\)\..+", detail))) else "other"
        values.append(ProbeObservation(test_id=probe.test_id, outcome=outcome, failure_type=failure_type, detail=detail))
    return tuple(values)


def _tap(report: bytes, plan: InvestigationPlan, native_exit: int) -> tuple[ProbeObservation, ...]:
    """Admit Node's standard TAP subtest aggregate; unsupported TAP is refused."""
    if type(report) is not bytes or not report or len(report) > _MAX_REPORT_BYTES:
        raise ValueError("TAP report is outside the admitted byte envelope")
    try:
        text = report.decode("utf-8")
    except UnicodeError as error:
        raise ValueError("TAP report is not UTF-8") from error
    probes = (plan.control, plan.security)
    names = {probe.selector.name: probe for probe in probes}
    if len(names) != 2:
        raise ValueError("TAP selectors are ambiguous")
    results: dict[str, tuple[bool, str, list[str]]] = {}
    blocks: dict[str, list[str]] = {}
    current = last = None
    plans, previous, version, summary = [], 0, False, {}
    for line in text.splitlines():
        if re.match(r"\s*Bail out!", line, re.IGNORECASE):
            raise ValueError("TAP stream bailed out")
        if line == "TAP version 13":
            if version:
                raise ValueError("Duplicate TAP version")
            version = True
            continue
        header = _TAP_SUBTEST.fullmatch(line)
        if header:
            if current is not None:
                raise ValueError("TAP subtest lacks a result")
            name = header["name"]
            if name not in names or name in blocks:
                raise ValueError("Unexpected or duplicate TAP subtest")
            current, last, blocks[name] = name, name, []
            continue
        plan_match = _TAP_PLAN.fullmatch(line)
        if plan_match:
            if current is not None:
                raise ValueError("Nested TAP plan is unsupported")
            plans.append(int(plan_match["count"]))
            continue
        result = _TAP_RESULT.fullmatch(line)
        if result:
            if current is None or result["name"] != current or int(result["number"]) != previous + 1:
                raise ValueError("Unexpected TAP top-level result")
            directive = (result["directive"] or "").lower()
            if directive == "todo" or (directive == "skip" and result["not"]):
                raise ValueError("TAP directive hides its outcome")
            results[current] = (bool(result["not"]), directive, blocks[current])
            previous, current = int(result["number"]), None
            continue
        if current is not None:
            blocks[current].append(line)
        elif last is not None and (not line or line[0].isspace()):
            blocks[last].append(line)
        elif line.startswith("#"):
            match = re.fullmatch(r"# (?P<key>tests|pass|fail|skipped|todo|cancelled)\s+(?P<count>\d+)", line)
            if match:
                if match["key"] in summary:
                    raise ValueError("Duplicate TAP summary")
                summary[match["key"]] = int(match["count"])
        elif not line:
            continue
        else:
            raise ValueError("Unsupported TAP aggregate structure")
    if current is not None or not version or plans != [len(probes)] or set(results) != set(names):
        raise ValueError("Incomplete TAP aggregate")
    observations = []
    for probe in probes:
        failed, directive, block = results[probe.selector.name]
        detail = "\n".join(block)[:2048]
        if directive == "skip":
            outcome, failure_type = "skipped", None
        elif not failed:
            outcome, failure_type = "passed", None
        else:
            compact = re.sub(r"[^a-z0-9]", "", detail.lower())
            assertion = "errassertion" in compact or "assertionerror" in compact or "nativetestmorefailedtest" in compact
            outcome, failure_type = "failed", "assertion" if assertion else "other"
        observations.append(ProbeObservation(test_id=probe.test_id, outcome=outcome, failure_type=failure_type, detail=detail))
    expected_summary = {"tests": len(observations), "pass": sum(item.outcome == "passed" for item in observations),
                        "fail": sum(item.outcome == "failed" for item in observations),
                        "skipped": sum(item.outcome == "skipped" for item in observations)}
    if any(summary[key] != value for key, value in expected_summary.items() if key in summary):
        raise ValueError("TAP summary conflicts with top-level subtest outcomes")
    if native_exit != sum(item.outcome == "failed" for item in observations):
        raise ValueError("TAP exit conflicts with reported subtest outcomes")
    return tuple(observations)


def _minitest(report: bytes, plan: InvestigationPlan, root: str) -> tuple[ProbeObservation, ...]:
    probes = (plan.control, plan.security)
    for probe in probes:
        try:
            identity = RubyTestId.parse(probe.test_id)
        except ValueError as error:
            raise ValueError("Minitest identity is not native") from error
        if (identity.path, identity.class_name, identity.method) != (probe.path, probe.selector.classname, probe.selector.name):
            raise ValueError("Minitest identity and selector metadata disagree")
    cases = parse_minitest(report, tuple(probe.test_id for probe in probes), root=root,
                           test_paths=frozenset(probe.path for probe in probes), max_bytes=_MAX_REPORT_BYTES)
    values = []
    for case in cases:
        failure = case.failure
        assertion = bool(failure and case.outcome == "failed" and failure.kind == "failure"
                         and (failure.type == "Minitest::Assertion" or _assertion(failure.type or "", failure.message)))
        values.append(ProbeObservation(test_id=case.test_id, outcome=case.outcome,
                                       failure_type="assertion" if assertion else (failure.type or "other") if failure else None,
                                       detail=failure.message[:2048] if failure else ""))
    return tuple(values)


class NativeTests:
    """Run actual setup, collection, two probes and prescribed checks once."""

    def __init__(self, config: OperatorConfig, store: Store, sandbox: Sandbox | None = None):
        self.config, self.store = config, store
        self.sandbox = sandbox if sandbox is not None else Sandbox(config, store)

    @staticmethod
    def _planned_pair(plan: InvestigationPlan, pair: dict[str, str]):
        if plan.status != "planned" or not plan.control or not plan.security or not plan.recipe:
            raise ValueError("A complete native plan is required")
        probes = (plan.control, plan.security)
        if type(pair) is not dict or set(pair) != {p.path for p in probes}:
            raise ValueError("Exactly the two assigned probe files are required")
        for probe in probes:
            source = pair[probe.path]
            if not isinstance(source, str) or not source.strip() or len(source.encode()) > 65536 or len(probe.test_id.encode()) > 512:
                raise ValueError("Native probe source or identity exceeds its bound")
        return probes

    def _stdout(self, command: CommandResult) -> bytes:
        if command.stdout_ref is None:
            raise ValueError("Native stdout artifact is missing")
        data = self.store.get(command.stdout_ref)
        if len(data) > _MAX_REPORT_BYTES:
            raise ValueError("Native collection output exceeded its bound")
        return data

    def _discovery(self, command: CommandResult, plan: InvestigationPlan) -> bool:
        if command.status != "completed" or command.exit_code != 0:
            return False
        try:
            data = self._stdout(command)
            text, format = data.decode("utf-8", "strict"), plan.recipe.discovery_format
            if format == "lines":
                items = text.splitlines()
            elif format == "pytest":
                lines = [value.strip() for value in text.splitlines() if value.strip()]
                items = [line for line in lines if not re.fullmatch(r"\d+ tests? collected in [\d.]+s", line)]
            elif format == "junit-xml":
                tree = admit_xml(data, _MAX_REPORT_BYTES)
                keys = {(p.selector.classname, p.selector.name): p.test_id for p in (plan.control, plan.security)}
                items = [keys.get((case.get("classname", ""), case.get("name", "")), "unknown") for case in tree.iter("testcase")]
            elif format == "jest-json":
                items = [probe.test_id for probe, _, _, _ in _jest_entries(data, plan, self.config.sandbox.workspace_root, listing=True)]
            elif format == "ctest-json":
                items = [value["name"] for value in _document(data, "CTest")["tests"]]
            else:
                return False
            expected = {plan.control.test_id, plan.security.test_id}
            return len(items) == 2 and len(set(items)) == 2 and set(items) == expected
        except (ValueError, KeyError, TypeError, UnicodeError):
            return False

    def _observations(self, report: bytes, plan: InvestigationPlan, native_exit: int) -> tuple[ProbeObservation, ...]:
        format = plan.recipe.report_format
        if format == "junit":
            observed = _junit(report, plan)
        elif format == "jest":
            observed = _jest(report, plan, self.config.sandbox.workspace_root)
        elif format == "tap":
            observed = _tap(report, plan, native_exit)
        elif format == "minitest-json":
            observed = _minitest(report, plan, self.config.sandbox.workspace_root)
        else:  # The contract is closed, but preserve a strict refusal if it changes.
            raise ValueError("Unsupported native report format")
        failures = sum(item.outcome in ("failed", "error") for item in observed)
        if format != "tap" and ((failures == 0 and native_exit != 0) or (failures > 0 and native_exit == 0)):
            raise ValueError("Native exit conflicts with reported testcase outcomes")
        return observed

    @staticmethod
    def _collision(snapshot: SourceSnapshot, plan: InvestigationPlan) -> bool:
        paths = [*(file.path for file in snapshot.files), plan.control.path, plan.security.path]
        report = plan.recipe.report_path
        return any(report == path or report.startswith(path + "/") or path.startswith(report + "/") for path in paths)

    @staticmethod
    def _check_stop(stop_requested: Callable[[], bool] | None) -> None:
        if stop_requested is not None and stop_requested():
            raise _NativeCancellation("operator_cancelled_at_command_boundary")

    def execute(self, snapshot: SourceSnapshot, plan: InvestigationPlan, pair: dict[str, str], run_id: str,
                revision: str = "baseline", generation: int = 1, *,
                stop_requested: Callable[[], bool] | None = None) -> RevisionExecution:
        if revision not in ("baseline", "candidate"):
            raise ValueError("Unknown revision")
        commands, lease, observations = [], None, ()
        cleanup, status, detail, discovery_ok, report_ref, regression = "unknown", "blocked", "", False, None, None
        try:
            self._planned_pair(plan, pair)
            if self._collision(snapshot, plan):
                raise ValueError("Frozen report path collides with captured source or a probe")
            if any(probe.path in {file.path for file in snapshot.files} for probe in (plan.control, plan.security)):
                raise ValueError("Probe path would overwrite a captured source file")
            self._check_stop(stop_requested)
            lease = self.sandbox.acquire(run_id, generation, snapshot.manifest)
            self._check_stop(stop_requested)
            self.sandbox.stage(lease, snapshot, {path: text.encode() for path, text in pair.items()})

            def execute(argv, suffix):
                self._check_stop(stop_requested)
                result = self.sandbox.execute(lease, argv, f"native.{digest({'run': run_id, 'generation': generation, 'revision': revision, 'step': suffix})}",
                                              workdir=self.config.sandbox.workspace_root)
                commands.append(result)
                if result.status != "completed":
                    raise SandboxBoundaryError("Native command incomplete: " + result.status)
                return result

            for index, argv in enumerate(plan.recipe.setup_commands):
                if execute(argv, f"setup.{index}").exit_code != 0:
                    raise ValueError("Native setup did not pass")
            discovery = execute(plan.recipe.discovery_command, "discovery")
            discovery_ok = self._discovery(discovery, plan)
            if not discovery_ok:
                raise ValueError("Native discovery did not name exactly the frozen two-probe identity set")
            executed = execute(plan.recipe.execution_command, "execution")
            report = self.sandbox.read_predeclared_report(lease, plan.recipe.report_path, _MAX_REPORT_BYTES)
            report_ref = self.store.put(report)
            try:
                observations = self._observations(report, plan, executed.exit_code if executed.exit_code is not None else -1)
            except ValueError as error:
                status = "invalid_report"
                raise ValueError("Native report was not admitted: " + str(error)) from error
            if revision == "candidate":
                regression = True
                for index, argv in enumerate(plan.recipe.regression_commands):
                    regression = execute(argv, f"regression.{index}").exit_code == 0 and regression
                if not plan.recipe.regression_commands:
                    regression = all(item.outcome == "passed" for item in observations)
                    detail = "Only the two reviewed probe outcomes were prescribed; no broader regression-suite claim."
            status = "completed"
        except _NativeCancellation as error:
            status, detail = "blocked", str(error)
        except SandboxBoundaryError as error:
            status, detail = "unknown", str(error)[:4096]
        except Exception as error:  # noqa: BLE001 - foreign-library boundary: explicit failed/unknown outcome
            detail = f"{type(error).__name__}: {error}"[:4096]
        finally:
            if lease is not None:
                try:
                    cleanup = self.sandbox.release(lease)
                except Exception as error:  # noqa: BLE001 - foreign-library boundary: explicit failed/unknown outcome
                    cleanup = "unknown"
                    detail += f"; cleanup: {type(error).__name__}"
        return RevisionExecution(revision=revision, source_manifest=snapshot.manifest, pair_sha256=digest(pair),
                                 image=self.config.sandbox.image, policy_sha256=self.sandbox.profile_identity()["policy_sha256"],
                                 sandbox_id=lease.sandbox_id if lease else "", discovery_ok=discovery_ok,
                                 observations=observations, execution_status=status, commands=tuple(commands), report_ref=report_ref,
                                 cleanup=cleanup, regression_passed=regression, detail=detail)
