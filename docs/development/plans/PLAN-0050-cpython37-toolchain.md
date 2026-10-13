---
id: PLAN-0050
kind: plan
title: CPython 3.7 toolchain image and older pytest
status: in_progress
updated: 2026-10-13
related: [SPEC-0046, SPEC-0033, SPEC-0037]
---

# CPython 3.7 toolchain image and older pytest

## Objective and dependencies

Implement [SPEC-0046](../specs/SPEC-0046-cpython37-toolchain.md): a CPython 3.7 image row and pytest 6 to 7 support in the runner, parser and probe, qualified live on RIG0. Depends on the kind cluster and OpenShell on RIG0 (one thread at a time) and on SPEC-0042's matrix (draft PR #48) for the row. The JDK 8 image is built in parallel by another thread; shared files (matrix, `prepare_toolchains.py`, `test_toolchains.py`, CURRENT.md) are coordinated by message.

## Steps

- [x] Record real pytest 4.6.11, 5.4.3, 6.0.2, 6.2.5, 7.0.1, 7.2.0 and 7.4.4 output on CPython 3.7.17 with the operator prefix and check the runner and parser against it.
- [x] Make the probe load on 3.7 and pytest 6+, record an unsupported runtime and refuse it by name; regenerate the evidence-assessment set.
- [x] Add `deploy/qualification/toolchains/python37`, per-directory receipts, `TOOLCHAINS=` selection and the 3.7 gate; build it offline locally.
- [x] Add `make qualify-python37-case` for CVE-2021-32839 and let the workspace bound be raised to 512 entries by the operator.
- [ ] Live on RIG0: fresh kind node, `TOOLCHAINS=python37` build, load and gate; the real case.
- [ ] Add the `cpython-3.7-pytest` matrix row and widen the pytest framework row with the gate report as evidence; regenerate the SPEC-0042 report.
- [ ] Review, CURRENT.md, handoff.

## Validation and progress

2026-10-13, cloud container (not qualification). Real output: 6.0.2 to 7.4.4 discover both ids (6.x in another order), run with exit 1, and parse to control passed, security failed `AssertionError` at `tests/test_case.py:14`; baseline summaries are admitted by `frameworks.py` unchanged. 4.6.11 and 5.4.3 exit 4 on `--import-mode=importlib`. The same driver on CPython 3.12.3 with pytest 6.2.5, 7.4.4, 8.3.5 and 9.0.3 admitted the witness (path reached, effect observed) after the hook-wrapper change; on 3.7 every version ran the tests with the probe injected and recorded `CPython 3.7.17 has no sys.monitoring (3.12+)`. Before the change, the probe would crash the 3.7 bootstrap (`sys.monitoring` missing) and lose the run.

Image: `docker build --network=none` of the python37 context from `python@sha256:b53f496c…` (CPython 3.7.17, pip 23.0.1) installed the nine hash-pinned wheels; fixture control passed (`tests="1"`, `test_native_roundtrip`); syntax, no-tests and assertion exits 2, 5 and 1. `prepare_toolchains build --language python37` itself stopped at `docker pull` with Docker Hub 429 in the container; it runs on RIG0. CVE-2021-32839 host fetch in the container reproduced both #42 manifest digests exactly.

`make test-config`: 997 passed on 6be1b5f before the gate files; 1064 passed after merging main 42a7273 with everything above.

Al's review of 72b6861 (P2): `TOOLCHAINS` reached pytest as a `-k` substring, so `TOOLCHAINS=python` also selected the 3.7 gate and `"python java"` was an invalid expression (exit 4). Fixed with exact `--toolchain` selection from marker arguments; collection-only regressions in `tests/configuration/test_toolchain_selection.py`.

## Decisions and next action

Qualified floor pytest 6.0 (importlib mode); witness on 3.7 refused by name rather than a weaker observer; matrix row only after the live gate. Next: ask for the kind cluster, then run the live steps on RIG0 under `/home/al/git/corsair/.worktrees/claude/toolchain-python37-drklks` with evidence under `/home/al/git/corsair/.runs`.
