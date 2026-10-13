---
id: SPEC-0046
kind: spec
title: CPython 3.7 toolchain image and pytest 6 to 7 runner support
status: draft
updated: 2026-10-13
related: [SPEC-0007, SPEC-0028, SPEC-0032, SPEC-0033, SPEC-0037, PLAN-0050]
---

# CPython 3.7 toolchain image and pytest 6 to 7 runner support

## Goal and scope

SPEC-0042 (runtime selection, draft PR #48) found that no fetched Python benchmark case runs on the CPython 3.12 image: none of their CI tests 3.12, and the runtime that satisfies the most of them is CPython 3.7 (nine cases). Several also declare pytest older than 9 (`>=3,<=6.2.5`, `>=6,<7`, `==7.2.0`). This component adds one operator-owned image row for CPython 3.7 and makes the native pytest runner, its JUnit parser and the SPEC-0033 witness probe work with the pytest releases a 3.7 project can install.

In scope: a digest-pinned upstream `python:3.7-slim` image with hash-pinned offline pytest 7.4.4 (the last release supporting 3.7) and the same fixture and gate checks as the 3.12 image; the runner, parser and probe over pytest 6.0 to 7.4 on 3.7 and pytest 6.2 to 9.0 on 3.12; one live run of the runner on a real 3.7 case. Excluded: dependency installation for a case (the environment agent's setup, SPEC-0026), pytest below 6.0, other Python versions, and any change to the gates or agent contracts.

## Boundaries and design

**Image.** `deploy/qualification/toolchains/python37` mirrors the 3.12 directory: `Dockerfile` from `docker.io/library/python@sha256:b53f496c…` (CPython 3.7.17 on Debian 12, pip 23.0.1), `requirements.txt` with one SHA-256 per wheel, `wheels.json` (the same nine wheels plus `six` for the dependency diagnostic), and the same `test_native.py`. `prepare_toolchains` builds every Python directory with `--network=none` from wheels fetched and hash-checked on the host; `TOOLCHAINS=python37` limits build and load to that directory (the `--language` option shared with the JDK 8 thread) and the gate to the gates whose images are all named (`--toolchain`, from each gate's `toolchain` marker arguments); a list no gate covers, or an unknown name, is a usage error, so a partly prepared set never starts an unprepared sandbox. A receipt now covers only its own directory's sources, so adding an image does not invalidate the others' receipts.

**Runner and parser.** No code change is needed for pytest 6.0 to 7.4: real `--collect-only -q` output, JUnit XML (xunit2 default since 6.0, `junit_logging=all`, `--tb=native`) and the baseline `1 passed in Ns` summary from each of 6.0.2, 6.2.5, 7.0.1, 7.2.0 and 7.4.4 on CPython 3.7.17 are committed under `tests/unit/pytest_reports/` and checked offline. pytest 6.x lists importlib-mode items in a different order; the runner already compares sets. pytest 4.6 and 5.4 parse too but reject the operator prefix's `--import-mode=importlib` (exit 4), so the qualified floor is 6.0; the floor is documented, not enforced, until the matrix row lands. The OpenShell test workspace keeps its 64-entry default and now lets the operator raise the bound to 512 entries for a small real tree; larger trees wait for in-sandbox source fetch (SPEC-0025).

**Probe.** Observation needs CPython 3.12+ (`sys.monitoring`; audit hooks are 3.8+ and `co_qualname` 3.11+). The probe used a new-style hook wrapper (pluggy 1.1+) and `pytest.ExitCode` (pytest 5+), so on 3.7 the bootstrap crashed before pytest ran and the test run itself was lost. Now the probe loads on any CPython 3.7+ and pytest 6+ (old-style `hookwrapper`, literal exit status 3); on a runtime without `sys.monitoring` it registers nothing, lets pytest run unchanged and writes a record whose new `unsupported` field names the runtime. The record schema becomes `corsair-witness-v2`; `witness_evidence` refuses such a record by name (`witness probe unsupported on this runtime: CPython 3.7.17 …`), so the gate treats the witness as absent and the verdict stays inconclusive or not verified by design. No weaker 3.7 observer (profile hooks plus wrapped `open`) is built: it would miss C-level opens and widen a claim the 3.12 probe makes.

**Matrix.** The `cpython-3.7-pytest` row is added to `deploy/runtime-matrix.yaml` only after the live toolchain gate passes, with that report as its evidence, together with a second pytest framework row `versions: ">=6.0,<8"`, `images: [cpython-3.7-pytest]` (per-image framework scoping, added to SPEC-0042 in #48 at dbbb980); the existing pytest row is scoped to `cpython-3.12-pytest` and widened only to what was checked on 3.12. Until then selection is unchanged.

## Acceptance and validation

Offline: the recorded outputs parse to the two expected ids, outcomes and failure location for every version; the probe test removes `sys.monitoring` in a real subprocess and checks that pytest ran, the record names the runtime and the mapping refuses it; the evidence-assessment set is regenerated (only the probe digest, schema and new field change); `make test-config`. Local image check (not qualification): offline build, fixture control and the syntax/no-tests/assertion exit codes on CPython 3.7.17.

Live, on a fresh kind node with OpenShell on RIG0: `make toolchain-images toolchain-images-load qualify-toolchain TOOLCHAINS=python37` (image identity, offline fixture and diagnostics, cold hash-checked dependency install, missing-artifact and unavailable-registry diagnostics, cleanup); `make qualify-python37-case` (CVE-2021-32839 at both #42 commits, captures matching `benchmarks/source-pins.json`, discovery, execution, JUnit admission, probe refusal by name, cleanup). The case's upstream regression test is functional and passes at both commits, so the run is not a disposition.

## Decisions and open questions

Direction: the coordinator's brief for Al's goal of running every benchmark case and Al's rule of one digest-pinned upstream image per runtime version with no nearby-version fallback. Open: a witness for 3.8 to 3.11 (audit hooks exist there, `sys.monitoring` does not); the case's own pinned pytest is installed by setup, which is not built yet. Plan: [PLAN-0050](../plans/PLAN-0050-cpython37-toolchain.md).
