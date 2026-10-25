---
id: HANDOFF-recommendation-probe-deadline
kind: handoff
title: Recommendation implementation — trusted probe deadline
status: ready_for_parent_qualification
updated: 2026-10-25
base: c0bd5b9783ed00ffceea99d820fb72f2e4035117
---

# Parent handoff: trusted probe deadline

## Implemented boundary

The trusted in-image driver no longer imposes an independent 120-second timeout on
its pytest subprocess. `DockerSandbox` continues to own the sole validated
`probe_timeout_seconds` wall-clock deadline, container stop, and immutable
label/identity cleanup. The driver's coverage JSON operation still has a deliberate
30-second reporting allowance, but the active outer container deadline bounds it.
No host target execution or policy relaxation was introduced.

The existing one-second timeout and cleanup test remains. A new
`@pytest.mark.docker` and `@pytest.mark.long_probe` integration regression is gated
by `CORSAIR_TEST_LONG_PROBE=1`; it performs one real control probe that sleeps 121
seconds and must return valid evidence and cleanup before a 180-second budget. The
marker is registered in `pyproject.toml` and it is discovered by the Docker selection.

Documentation states that the trusted image must be rebuilt with `just images`; a
driver-content rebuild changes the immutable manifest image ID even when unchanged
settings retain the same `Settings.identity`. Recipe/budget intent digests and
settings/image/runtime identity must not be reused for an existing operation.

## Actual focused results

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD" \
  /Users/al/git/corsair/.venv/bin/python -m pytest -q -W error \
  -m 'not docker and not temporal and not live' \
  tests/unit/test_evidence.py tests/integration/test_docker.py
```

Result: `7 passed, 8 deselected in 0.40s`.

```bash
/Users/al/git/corsair/.venv/bin/ruff check \
  src/corsair/adapters/sandboxing/driver.py tests/integration/test_docker.py
/Users/al/git/corsair/.venv/bin/ruff format --check \
  src/corsair/adapters/sandboxing/driver.py tests/integration/test_docker.py
PYTHONDONTWRITEBYTECODE=1 /Users/al/git/corsair/.venv/bin/ty check \
  --python /Users/al/git/corsair/.venv \
  src/corsair/adapters/sandboxing/driver.py tests/integration/test_docker.py
git diff --check
git diff --exit-code c0bd5b9783ed00ffceea99d820fb72f2e4035117 -- evals/fixtures
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD/src:$PWD" \
  /Users/al/git/corsair/.venv/bin/python -m pytest --collect-only -q -m docker \
  tests/integration/test_docker.py
```

Result: Ruff lint passed, both Python files were already formatted, ty passed, no
whitespace errors occurred, zero frozen-fixture files differ from base, and 8 Docker
tests collected. Collection and deselection do not execute Docker.

## Parent-required gates

No Docker/image build, native target execution, Temporal service, live provider,
package build, full suite, or CI ran here. In particular, the new 121-second
regression is **unrun**, so it must not be reported as passed.

From this worktree, rebuild before the native test:

```bash
just images
CORSAIR_TEST_LONG_PROBE=1 just -- test-docker -q -W error \
  tests/integration/test_docker.py::test_real_docker_probe_deadline_can_exceed_120_seconds
```

Then run the retained short timeout/cleanup case and the parent's required native,
package, and CI gates. Preserve the changed image ID, runtime/configuration identity,
and any actual native result in the parent delivery receipt.

## Final native qualification and publication boundary

Final source imports were asserted against this worktree while using the one immutable root environment. `nix develop --no-update-lock-file --command just check` and the full `just test-all -q -W error` gate passed **152 tests**, with zero skips. Tests include actual SDK workers, Docker, CLI processes and a fresh installed wheel; scripted agent fixtures remain distinguished from real inference. The explicit 121-second target probe completed before its 180-second outer deadline using the separately built review image; Linux native CI enables this test. The packaged risk digest changes capability identity, and v2 execution intents bind that digest. Existing v1 claims remain retained and mismatched reconciliation is explicit, not silently migrated. The [sanitized receipt](../../../../evals/baselines/qualifications/qualification-probe-deadline-2026-10-25.json) records precise scope and unknown cost. This is an independent PR against the recorded base; no main-branch merge is authorized. Exact pushed commit/CI results are external delivery receipts, not retroactively rewritten historical claims.
