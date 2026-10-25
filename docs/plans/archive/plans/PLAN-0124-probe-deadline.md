---
id: PLAN-0124
kind: plan
title: Trusted probe deadline ownership
status: implemented_pending_native_qualification
updated: 2026-10-25
base: c0bd5b9783ed00ffceea99d820fb72f2e4035117
---

# Trusted probe deadline ownership

## Goal and bounded scope

Remove only the trusted in-container driver's independent 120-second cap around
`coverage run -m pytest`. The validated `Budget.probe_timeout_seconds` enforced by
`DockerSandbox` remains the single wall-clock deadline for the full container role
and remains the owner of stop-and-cleanup behavior. There is no host target-execution
path.

The driver retains a named 30-second timeout for its post-pytest `coverage json`
report. The outer DockerSandbox wait begins with the container and therefore still
bounds that reporting subprocess; it cannot extend the role's configured deadline.

## Implementation decisions

- `driver.py` no longer passes a timeout to the target pytest subprocess and removes
  the now-unreachable pytest `TimeoutExpired` exception path.
- `DockerSandbox._wait_with_heartbeat` is unchanged: it validates the configured
  probe timeout through `Budget`, stops the immutable labeled container at expiry,
  and its `finally` path independently confirms cleanup.
- The existing one-second timeout/cleanup integration regression is retained.
- `test_real_docker_probe_deadline_can_exceed_120_seconds` is a real-Docker,
  `long_probe`-marked test. It is additionally gated by
  `CORSAIR_TEST_LONG_PROBE=1`, executes one control role that sleeps 121 seconds,
  requires a successful trusted driver record before its 180-second probe budget,
  and confirms immutable-label cleanup. It is intentionally not an ordinary fast
  or default native gate.
- No frozen fixture, source hash, existing operation label, resource limit,
  credential boundary, target network policy, or Docker runtime policy changed.

## Runtime and evidence identity

The driver is copied into the trusted image by `deploy/python/Dockerfile`. The parent
must run `just images` from this worktree after this change before running native
Docker tests or a reference replay. A changed driver under the same image tag has a
new immutable image ID recorded in `RunManifest`; unchanged settings JSON preserves
`Settings.identity`, which hashes settings rather than image bytes. Recipe and budget
changes are separately bound in each execution intent, while settings changes such as
`image` or `runtime` change the configuration digest. Existing operations must not be
reconciled or reused across any changed recipe, budget, settings, or image-runtime
identity.

## Actual focused validation

The following commands made no Docker, Temporal, live-provider, model, installation,
or host-target-execution call:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD" \
  /Users/al/git/corsair/.venv/bin/python -m pytest -q -W error \
  -m 'not docker and not temporal and not live' \
  tests/unit/test_evidence.py tests/integration/test_docker.py
```

Result: `7 passed, 8 deselected in 0.40s`. The deselected tests include the retained
short native timeout/cleanup regression and the new long real-Docker regression.

```bash
/Users/al/git/corsair/.venv/bin/ruff check \
  src/corsair/adapters/sandboxing/driver.py tests/integration/test_docker.py
/Users/al/git/corsair/.venv/bin/ruff format --check \
  src/corsair/adapters/sandboxing/driver.py tests/integration/test_docker.py
PYTHONDONTWRITEBYTECODE=1 /Users/al/git/corsair/.venv/bin/ty check \
  --python /Users/al/git/corsair/.venv \
  src/corsair/adapters/sandboxing/driver.py tests/integration/test_docker.py
```

Result: Ruff lint passed, both files were already formatted, and ty passed with the
pinned root environment.

```bash
git diff --check
git diff --exit-code c0bd5b9783ed00ffceea99d820fb72f2e4035117 -- evals/fixtures
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD" \
  /Users/al/git/corsair/.venv/bin/python -m pytest --collect-only -q -m docker \
  tests/integration/test_docker.py
```

Result: no whitespace errors, zero frozen-fixture files differ from the base, and all
8 Docker tests (including the new long-probe test) collected. Collection does not run
Docker or prove native execution.

## Required parent gates

The new long regression has **not** passed: no Docker daemon, image rebuild, target,
Temporal service, model, provider, live workflow, package build, or complete suite
was run in this worktree. The parent should rebuild the trusted image and then run:

```bash
just images
CORSAIR_TEST_LONG_PROBE=1 just -- test-docker -q -W error \
  tests/integration/test_docker.py::test_real_docker_probe_deadline_can_exceed_120_seconds
```

Then run the ordinary affected Docker timeout/cleanup regression and the repository's
required native, package, and CI qualification gates under the reviewed host policy.
A scripted/fake result, collection-only result, or this focused offline result is not
evidence that the 121-second Docker path passed.

## Final implementation stage

The bounded implementation is complete. Final pinned Just/Ruff/ty/documentation checks passed; the physical-Mac complete suite passed 152 tests with zero skips. Native timing and qualification scope are recorded in the branch receipt. Earlier focused-test notes retain their original stage context; this section records the final native stage. Frozen inputs/pins were not changed. No cost or production readiness claim is made.
