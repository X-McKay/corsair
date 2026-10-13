---
id: PLAN-0076
kind: plan
title: Runtime inferred from framework metadata when undeclared
status: in_progress
updated: 2026-10-13
related: [SPEC-0069, SPEC-0042, PLAN-0073]
---

# Runtime inferred from framework metadata when undeclared

## Objective and dependencies

Implement [SPEC-0069](../specs/SPEC-0069-inferred-runtime.md) offline in `nodes/runtime/matrix.py` and the matrix file, with the report and runtime-stage reason showing the inferred basis. It builds on #97 (SPEC-0067 corpus and report section). The smoke test for projects without tests is a separate component after this.

## Steps

- [x] `Supported.runtime_basis` and `inferred_from`; `InferenceRow` and `Matrix.inference` with the runtime guard; inferred selection path in `select`.
- [x] Seven inference rows from release metadata (pytest 9.0, 7.2/7.4, 6.2/7.0, 6.0; Jest 24.8/24.9 and 29; Test::More 1.302073), each checked at its source on 2026-10-13.
- [x] Report outcome and runtime-stage reason name the inferred basis.
- [x] Unit tests (`tests/unit/test_runtime_inference.py`).
- [x] Two Minitest rows after #99 (5.14.4/5.15.0: Ruby >=2.2,<4.0; 5.27.0: Ruby >=3.1).
- [x] Regenerated the report on main `184e609` with the inference rows: corpus 3 supported (image-only), 22 supported (runtime inferred), 4 supported (image-only, runtime inferred), 7 unsupported, 6 undetermined; benchmark unchanged.
- [ ] Review, records, PR.

## Validation and progress

Sources read 2026-10-13: PyPI JSON `requires_python` for pytest 9.0.0 and 9.0.3 (>=3.10), 7.4.4 and 7.2.0 (>=3.7), 7.0.1 and 6.2.5 (>=3.6), 6.0.2 (>=3.5); npm registry `engines.node` for jest 24.8.0 and 24.9.0 (>= 6) and 29.0.0 and 29.7.0 (^14.15.0 || ^16.10.0 || >=18.0.0); `MIN_PERL_VERSION` 5.008001 in Test-More/test-more v1.302073 `Makefile.PL` ; rubygems.org API `ruby_version` for minitest 5.14.4, 5.15.0 (>= 2.2, < 4.0) and 5.27.0 (>= 3.1) (metacpan is refused by this container's proxy, GitHub raw is not).

Report on the corpus with these rows: 26 supported with an inferred runtime (22 Python on `cpython-3.12-pytest`, 4 Perl on `perl-5.26-make`, image-only), 3 supported declared, 7 unsupported (2 Java need JUnit 5.10; 5 Jest 29 need Node 14.15 or later), 6 undetermined (Vitest and Node's built-in runner have no row or framework; C has no detector). Benchmark outcomes unchanged; CVE-2019-10744 still names both its gaps.

Unit and runtime checks: see the PR for counts.

## Decisions and next action

Inference uses the test framework only (SPEC-0069). Next: the operator smoke test for projects that ship no tests, so the environment stage can admit the corpus cases.
