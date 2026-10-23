# Differential Probe and Verdict Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Python, JavaScript, Java and Perl use one Boolean differential probe whose role-relative results produce positive, scoped negative and honest nondecisive dispositions.

**Architecture:** Framework drivers turn the Boolean returned by `run_target(payload)` into `PASS` or `FAIL` according to the trusted role; exceptions and missing evidence remain separate results. The kernel requires target coverage and an outcome-blind audit before deriving a per-revision disposition, then derives fix status from the vulnerable/remediated pair.

**Tech Stack:** Python 3.12, Pydantic, PydanticAI, pytest/AnyIO, node:test, javac/Java 21, Perl/TAP, Docker sandbox port.

**Spec:** `docs/superpowers/specs/2026-10-23-multilingual-benchmark-and-improvement-loop-design.md`

## Global Constraints

- One submitted probe defines `CONTROL_PAYLOAD`, `EXPLOIT_PAYLOAD` and one `run_target(payload) -> bool`; submitted code never receives its role or expected answer.
- Public role results are exactly `PASS`, `FAIL`, `ERROR`, `NOT_RUN` and `INFRA`.
- `LIKELY_EXPLOITABLE` requires control `PASS`, exploit `PASS`, exact target-line coverage and an accepted blind audit.
- `LIKELY_NOT_EXPLOITABLE` requires control `PASS`, exploit `FAIL`, exact target-line coverage and an accepted blind audit; exceptions never qualify.
- Every role and revision runs in a separate fresh offline container; model-written code never runs on the host.
- The top-level label mirrors the source revision; each evaluated revision also retains its own disposition.
- A removed fixed target may be accepted as `INCONCLUSIVE/TARGET_REMOVED`, but fix status stays `not_verified`.
- Keep evaluator oracles out of `Case`, prompts, producer tools and auditor inputs.
- Run `make test-offline` for every task and `make test` for kernel, adapter, image or sandbox changes.

## Review Focus

- A clean `false` control result must be `FAIL`, not exploit evidence; pin this in `test_control_false_is_inconclusive` in Task 2.
- An accepted audit must be required for negative as well as positive labels; pin this in `test_audit_rejection_blocks_negative_disposition` in Task 2.
- Application exceptions that resemble fixed-side rejection must stay `ERROR`; pin this in each native adapter matrix in Task 3.
- A missing fixed target must retain `TARGET_REMOVED` and `not_verified`; pin this in `test_removed_fixed_target_is_accepted_but_not_verified` in Task 2.
- Old assertion-style Python submissions must be rejected as contract errors instead of having their polarity guessed; pin this in `test_python_driver_requires_boolean` in Task 3.

---

### Task 1: Restore a bounded, verified test baseline

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `tests/test_producer_auditor.py`

**Interfaces:**
- Consumes: the current PydanticAI producer tests.
- Produces: a locked dependency set where a minimal `FunctionModel` agent run completes and producer tests fail within ten seconds instead of hanging indefinitely.

- [ ] **Step 1: Add a bounded FunctionModel regression test**

Add `test_function_model_agent_run_completes` to `tests/test_producer_auditor.py`. Run `Agent(FunctionModel(...), output_type=str).run("hi")` inside `anyio.fail_after(10)` and assert the output is `"ok"`.

- [ ] **Step 2: Verify the locked 2.55.0 dependency fails**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_producer_auditor.py::test_function_model_agent_run_completes -v`

Expected: FAIL by the ten-second bound while `pydantic_graph` is blocked sending its first graph result.

- [ ] **Step 3: Pin the known-good PydanticAI release**

Change `pydantic-ai-slim[openai]` from `2.55.0` to `2.54.0` and regenerate `uv.lock` with `UV_CACHE_DIR=/tmp/corsair-uv-cache uv lock`.

- [ ] **Step 4: Verify the baseline**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache make test-offline`

Expected: PASS with no timeout.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock tests/test_producer_auditor.py
git commit -m "fix: pin working pydantic ai graph runner"
```

### Task 2: Define role results and per-revision dispositions in the kernel

**Files:**
- Modify: `src/corsair/kernel.py`
- Modify: `tests/fakes.py`
- Modify: `tests/test_kernel.py`
- Modify: `tests/test_evidence.py`

**Interfaces:**
- Consumes: adapter `Outcome` evidence temporarily, until Task 3 migrates the adapters.
- Produces: `RoleResult`, `RevisionDisposition`, `role_result(role: Role, outcome: Outcome) -> RoleResult`, and verdicts with `revisions: tuple[RevisionDisposition, ...]`.

- [ ] **Step 1: Write the result-mapping tests**

Add parameterized tests asserting: control/holds=`PASS`, control/violated=`FAIL`, exploit/violated=`PASS`, exploit/holds=`FAIL`, errored=`ERROR`, not-run=`NOT_RUN`, infra=`INFRA`.

- [ ] **Step 2: Write the decision-table tests**

Add kernel tests named `test_both_roles_pass_is_likely_exploitable`, `test_control_pass_exploit_fail_is_likely_not_exploitable`, `test_control_false_is_inconclusive`, `test_audit_rejection_blocks_negative_disposition`, and `test_exploit_error_never_becomes_negative`. Assert rule `K1` for positive, `K4` for negative and `K3` for nondecisive results.

- [ ] **Step 3: Write the fixed-revision tests**

Add `test_secure_fixed_revision_has_negative_disposition_and_verified_fix` and `test_removed_fixed_target_is_accepted_but_not_verified`. The latter must assert fixed label `INCONCLUSIVE`, reason code `TARGET_REMOVED`, and fix `not_verified`.

- [ ] **Step 4: Verify the new tests fail**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_kernel.py tests/test_evidence.py -v`

Expected: FAIL because `RoleResult`, `RevisionDisposition` and `LIKELY_NOT_EXPLOITABLE` do not exist.

- [ ] **Step 5: Implement the kernel types and decision function**

In `src/corsair/kernel.py`, add:

```python
class RoleResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    NOT_RUN = "NOT_RUN"
    INFRA = "INFRA"

class RevisionDisposition(Frozen):
    revision: RevisionName
    label: Label
    rule: str
    reason_code: str
    reason: str

def role_result(role: Role, outcome: Outcome) -> RoleResult: ...
```

Add `LIKELY_NOT_EXPLOITABLE` to `Label`, add `result: RoleResult` and `invariant_held: bool | None` to `ProbeRun`, and add `revisions` to `Verdict`. Keep `Outcome` private to the transitional normalized adapter evidence and exclude it from public run records after Task 3.

- [ ] **Step 6: Refactor `Kernel.evaluate` around complete evidence**

Run both roles when the control is a clean result, require coverage for either decisive exploit result, audit before interpreting the exploit role, and derive `K1` or `K4`. Return `INCONCLUSIVE` for a control `FAIL` or any invalid evidence. Detect a missing target file on the fixed tree before its build and emit `TARGET_REMOVED` without calling it verified.

- [ ] **Step 7: Verify the kernel tests pass**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_kernel.py tests/test_evidence.py -v`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/corsair/kernel.py tests/fakes.py tests/test_kernel.py tests/test_evidence.py
git commit -m "feat: add role-relative probe dispositions"
```

### Task 3: Migrate all four native drivers to the Boolean role contract

**Files:**
- Modify: `src/corsair/frameworks/base.py`
- Modify: `src/corsair/frameworks/reports.py`
- Modify: `src/corsair/frameworks/pytest_.py`
- Modify: `src/corsair/frameworks/node_test.py`
- Modify: `src/corsair/frameworks/javac_java.py`
- Modify: `src/corsair/frameworks/perl_tap.py`
- Modify: `tests/test_docker_pilot.py`
- Modify: `tests/test_javascript.py`
- Modify: `tests/test_java_perl.py`
- Modify: `cases/path-traversal-fixture/reference-submission.json`
- Modify: `cases/path-traversal-javascript/reference-submission.json`
- Modify: `cases/path-traversal-java/reference-submission.json`
- Modify: `cases/path-traversal-perl/reference-submission.json`

**Interfaces:**
- Consumes: `RoleResult` and `role_result` from Task 2.
- Produces: native evidence records `{role, result, invariant_held, exception_type, message}` whose JUnit/TAP state agrees with the role-relative result.

- [ ] **Step 1: Rewrite native adapter expectations in tests**

For each runtime, assert vulnerable runs `[PASS, PASS]`, fixed runs `[PASS, FAIL]`, all four exact target coverages, source `LIKELY_EXPLOITABLE`, fixed `LIKELY_NOT_EXPLOITABLE`, and fix `verified`. Add Boolean-type, application-exception, missing-result and native-report-disagreement variants.

- [ ] **Step 2: Add the Python stale-contract test**

Add `test_python_driver_requires_boolean`; an assertion-style `run_target` that returns `None` must produce `ERROR` with `TypeError`, never `PASS` or `FAIL`.

- [ ] **Step 3: Verify the native tests fail**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_docker_pilot.py tests/test_javascript.py tests/test_java_perl.py -v`

Expected: FAIL against the old Python assertion contract and invariant-only native assertions.

- [ ] **Step 4: Change every trusted driver**

Each driver must validate an actual Boolean/scalar Boolean, compute `expected = true` for control and `false` for exploit, write `PASS` when `invariant == expected`, and make the one native test fail only for clean `FAIL` or error. Bind trusted serialization and test functions before importing the probe, preserving current anti-tampering behavior.

- [ ] **Step 5: Normalize and cross-check evidence**

Change `read_probe` to accept only the new record schema and verify role, native test count, PASS/failure polarity, error/error polarity and target coverage. A stale `holds`/`violated` record must be `ERROR`, not translated.

Return `result` plus `invariant_held` from framework evidence and remove serialized `outcome` from `ProbeRun`. Internal observation helpers may remain private, but no run JSON, verdict, prompt or feedback may expose `HOLDS`/`VIOLATED`.

- [ ] **Step 6: Convert the four reference probes**

Make Python return the same Boolean invariant already returned by JavaScript, Java and Perl. Preserve identical setup, target call and invariant across payloads.

- [ ] **Step 7: Run native verification**

Run: `BUILDX_CONFIG=/tmp/corsair-buildx DOCKER_BUILD_FLAGS='--secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt' UV_CACHE_DIR=/tmp/corsair-uv-cache make test`

Expected: PASS for all non-live tests in four images.

- [ ] **Step 8: Commit**

```bash
git add src/corsair/frameworks tests cases/path-traversal-*/reference-submission.json
git commit -m "feat: unify native probe pass semantics"
```

### Task 4: Update producer, auditor and public contracts atomically

**Files:**
- Modify: `src/corsair/producer.py`
- Modify: `src/corsair/auditor.py`
- Modify: `src/corsair/agent-contracts.yaml`
- Modify: `src/corsair/skills/differential-probing/SKILL.md`
- Modify: `src/corsair/skills/python-pytest/SKILL.md`
- Modify: `src/corsair/skills/javascript-node-test/SKILL.md`
- Modify: `src/corsair/skills/java-javac/SKILL.md`
- Modify: `src/corsair/skills/perl-tap/SKILL.md`
- Modify: `tests/test_producer_auditor.py`
- Modify: `tests/test_contracts.py`

**Interfaces:**
- Consumes: Task 2 verdicts and Task 3 driver contract.
- Produces: producer feedback that treats either decisive label as a completed source disposition while still allowing positive/fixed retry feedback for a nonverified fix.

- [ ] **Step 1: Write prompt and skill contract tests**

Assert every runtime skill says Boolean return, role-aware `PASS`/`FAIL`, same invariant, no role input, and that exceptions are errors. Assert the producer prompt contains both decisive source dispositions and no user-facing `holds`/`violated` contract.

- [ ] **Step 2: Write producer-stop tests**

Add one scripted positive case and one scripted negative case. Both must stop after a decisive audited submission; only a positive result with a correctable fixed-side probe error may request another submission.

- [ ] **Step 3: Verify the tests fail**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_producer_auditor.py tests/test_contracts.py -v`

Expected: FAIL on old instructions and stop rules.

- [ ] **Step 4: Update producer and auditor wording**

Describe the invariant Boolean once, explain role-relative pass semantics, require the same payload-only differential path, and tell the producer that a valid exploit `FAIL` is negative evidence rather than a gate rejection.

- [ ] **Step 5: Update stop and feedback logic**

Stop on audited `LIKELY_EXPLOITABLE` or `LIKELY_NOT_EXPLOITABLE`; keep fixed-side retry only when the source is positive and the failure can change `not_verified` to `verified` without changing the source disposition.

- [ ] **Step 6: Verify producer contracts pass**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_producer_auditor.py tests/test_contracts.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/corsair/producer.py src/corsair/auditor.py src/corsair/agent-contracts.yaml src/corsair/skills tests/test_producer_auditor.py tests/test_contracts.py
git commit -m "docs: teach agents role-relative probe results"
```

### Task 5: Version the submission contract and update operator documentation

**Files:**
- Modify: `src/corsair/kernel.py`
- Modify: `src/corsair/cli.py`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/design.md`
- Modify: `docs/readiness.md`
- Modify: `Makefile`
- Modify: `tests/test_contracts.py`
- Modify: `tests/test_eval.py`

**Interfaces:**
- Consumes: Tasks 2–4.
- Produces: explicit submission schema `corsair-lite/differential-probe/2`; stale submissions fail before any sandbox execution.

- [ ] **Step 1: Write schema-version rejection tests**

Assert a missing or v1 probe contract is rejected with an actionable message and creates no sandbox; assert v2 submissions load and serialize deterministically.

- [ ] **Step 2: Verify the tests fail**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_contracts.py tests/test_eval.py -v`

Expected: FAIL because `Submission` has no explicit contract version.

- [ ] **Step 3: Add `contract_version` to `Submission`**

Use `Literal["corsair-lite/differential-probe/2"]`, update all reference submissions, and reject stale polarity rather than inferring it.

- [ ] **Step 4: Replace old terminology in operator documentation**

Update the kernel table, examples, exit behavior and fix semantics. Keep the scope statement for `LIKELY_NOT_EXPLOITABLE` adjacent to every public label description.

- [ ] **Step 5: Run complete deterministic verification**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache make test-offline`

Run: `BUILDX_CONFIG=/tmp/corsair-buildx DOCKER_BUILD_FLAGS='--secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt' UV_CACHE_DIR=/tmp/corsair-uv-cache make test`

Expected: both PASS.

- [ ] **Step 6: Record the model-eval status**

Run `make eval` only when the configured provider is available. Record it as passed, failed or blocked; a provider failure cannot be reported as a contract pass.

- [ ] **Step 7: Commit**

```bash
git add src/corsair/kernel.py src/corsair/cli.py README.md AGENTS.md docs Makefile cases tests
git commit -m "docs: version the differential probe contract"
```
