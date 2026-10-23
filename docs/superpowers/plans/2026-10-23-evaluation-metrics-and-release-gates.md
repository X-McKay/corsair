# Evaluation Metrics and Release Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run controlled multi-model evaluations that report paired accuracy, latency, token use and cost by language, vulnerability type, framework and execution mode, and block releases below 80% overall or in any supported language.

**Architecture:** The evaluator writes one immutable run manifest and one row per fresh end-to-end attempt. A deterministic scorer joins those rows to evaluator-only corpus metadata, groups variants by vulnerability family, calculates first-attempt and within-N metrics, applies hard and graded gates, and renders JSON plus Markdown. A separate comparator accepts only hash-compatible runs.

**Tech Stack:** Python 3.12, Pydantic, PydanticAI usage records, pytest, existing provider profiles and CLI.

**Spec:** `docs/superpowers/specs/2026-10-23-multilingual-benchmark-and-improvement-loop-design.md`

## Global Constraints

- Implement after the probe/verdict and corpus-qualification plans.
- `RUNS` is the artifact directory. `ATTEMPTS` is the number of independent producer runs per case; never overload one with the other.
- “First attempt” means attempt index 1, including all producer corrections allowed inside that attempt's fixed submission/request/token budgets.
- Each attempt starts with a fresh producer workspace and fresh role containers. Reusing a provider client is allowed; reusing case state is not.
- A family receives one point only when every scored variant in that family produces the expected vulnerable disposition, remediated disposition/reason and fix status.
- Repeated attempts report stability and success-within-N; they never change first-attempt accuracy.
- Infrastructure failure blocks a release scorecard and remains in the denominator/status ledger.
- Deterministic hard failures cannot be averaged away by accuracy, latency or cost.
- Comparisons require identical dataset, prompt, skill, tool, image, policy, kernel, budget, attempt-count and sampling hashes.
- Credentials, provider secrets and unredacted private findings never enter manifests or reports.
- Live model evaluation is required for model-quality evidence. Scripted models and sandbox doubles test mechanics only.

## Review Focus

- A second-attempt success must not improve first-attempt accuracy; pin this in `test_retries_do_not_inflate_first_attempt_accuracy` in Task 3.
- Direct/script variants in one family must contribute one point; pin this in `test_family_macro_score_deduplicates_variants` in Task 3.
- Exactly 79% overall or for one language must fail; pin boundary tests in Task 4.
- A known-vulnerable `LIKELY_NOT_EXPLOITABLE` and known-fixed `LIKELY_EXPLOITABLE` must each fail an absolute gate even when aggregate accuracy exceeds 80%; pin both in Task 4.
- Missing provider usage fields must remain `null`, never zero; pin this in Task 2.
- Estimated cost must carry the exact pricing-table hash and effective entry; pin this in Task 2.
- Two runs with different skill or image hashes must be rejected as non-comparable; pin this in Task 5.

---

### Task 1: Define immutable run and attempt schemas

**Files:**
- Create: `src/corsair/evals.py`
- Modify: `src/corsair/cli.py`
- Modify: `src/corsair/artifacts.py`
- Modify: `tests/test_eval.py`

**Interfaces:**
- Produces: `RunManifest`, `AttemptRow`, `ExpectedPair`, `ObservedPair`, `PhaseLatencies`, `TokenUsage`, `CostUsage` and schema `corsair-lite/eval-run/3`.
- Consumes: qualified cases and metadata selected by `src/corsair/corpus.py`.

- [ ] **Step 1: Write schema and immutability tests**

Require run ID, UTC timestamps, dataset/split/version, provider and agent model names, sampling settings/seed, prompt/skill/policy/matrix/image/kernel/tool hashes, budgets, case/family/strata fields, expected and observed per-revision results, fix, gate/reason, artifact hashes and redacted error fields. Reject unknown fields and attempted overwrite of an existing run manifest.

- [ ] **Step 2: Verify the tests fail**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_eval.py -k 'manifest or attempt_schema' -v`

Expected: FAIL because v3 run types do not exist.

- [ ] **Step 3: Implement typed records and atomic writes**

Write `<RUNS>/<run-id>/manifest.json`, `attempts.jsonl`, `scorecard.json` and `scorecard.md`. Create the run directory exclusively, append one validated JSON line per completed attempt with flush/fsync, then finalize the manifest once. Retain child `run.json` artifact links by hash rather than copying transcripts into the scorecard.

- [ ] **Step 4: Hash every controlled input**

Hash provider JSON after removing secret values, producer/auditor prompts, all loaded producer skills, developer policy, matrix, runtime images, kernel/framework code, dataset manifest, oracle/reference revisions and budgets. Record missing image IDs as a blocking completeness error.

- [ ] **Step 5: Verify and commit**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_eval.py tests/test_contracts.py -v`

```bash
git add src/corsair/evals.py src/corsair/cli.py src/corsair/artifacts.py tests/test_eval.py
git commit -m "feat: record immutable evaluation attempts"
```

### Task 2: Capture phase latency, complete token usage and cost

**Files:**
- Modify: `src/corsair/kernel.py`
- Modify: `src/corsair/producer.py`
- Modify: `src/corsair/auditor.py`
- Modify: `src/corsair/providers.py`
- Modify: `src/corsair/evals.py`
- Create: `config/pricing.json`
- Modify: `tests/test_eval.py`
- Modify: `tests/test_producer_auditor.py`

**Interfaces:**
- Produces: acquisition, generation, audit, build, control, exploit and end-to-end monotonic durations; input, output, cached and reasoning token counts; provider-reported or versioned estimated USD cost.

- [ ] **Step 1: Write latency and usage tests**

Use a fake clock and scripted provider responses. Assert each phase is nonnegative, nested durations do not double-count the end-to-end total, source/fixed role timings remain separate, and unavailable token categories serialize as `null` rather than `0`.

- [ ] **Step 2: Write pricing tests**

Validate strict provider/model/effective-date entries and per-million-token decimal prices. Prefer provider-reported cost when present; otherwise estimate only when every billed category has a matching price. Record `source=provider|estimate|unavailable`, currency, pricing entry and pricing-file SHA-256.

- [ ] **Step 3: Verify the tests fail**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_eval.py tests/test_producer_auditor.py -k 'latency or token or cost or pricing' -v`

Expected: FAIL because only total duration and input/output tokens are currently captured.

- [ ] **Step 4: Instrument phase boundaries**

Use `time.monotonic_ns()` around acquisition, each producer request group, blind audit, build and each role execution. Keep UTC timestamps only for ordering and provenance. Attach phase records to evaluation artifacts so summaries cannot reconstruct timing from log text.

- [ ] **Step 5: Normalize provider usage**

Extract usage from PydanticAI response records without assuming every provider supplies cached/reasoning tokens or cost. Sum like categories across producer corrections and the auditor while retaining per-agent totals.

- [ ] **Step 6: Verify and commit**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache make test-offline`

```bash
git add src/corsair/kernel.py src/corsair/producer.py src/corsair/auditor.py src/corsair/providers.py src/corsair/evals.py config/pricing.json tests
git commit -m "feat: measure evaluation latency tokens and cost"
```

### Task 3: Run manifest-selected cases for independent attempts

**Files:**
- Modify: `src/corsair/cli.py`
- Modify: `src/corsair/evals.py`
- Modify: `Makefile`
- Modify: `tests/test_eval.py`

**Interfaces:**
- Produces: `corsair eval --manifest PATH --eval-set conformance|development|regression|release --attempts N` and corresponding `make eval CORPUS_MANIFEST=... EVAL_SET=... ATTEMPTS=... PROVIDER=...`.
- Removes: shell-expanded `--cases` as the release path; an explicit case filter may remain for focused development but must be marked non-release.

- [ ] **Step 1: Write attempt-isolation and selection tests**

Assert manifest selection excludes quarantine/unqualified cases, attempt indexes begin at 1, every attempt creates a new producer workspace/run ID and cleanup receipt, and a failure on one case does not suppress independent rows for the rest unless evaluator integrity is lost.

- [ ] **Step 2: Write first-attempt and family tests**

Add `test_retries_do_not_inflate_first_attempt_accuracy` and `test_family_macro_score_deduplicates_variants`. Include a family whose direct variant passes and script variant fails; the family must score incorrect once.

- [ ] **Step 3: Verify the tests fail**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_eval.py -k 'attempt or family or selection' -v`

Expected: FAIL because the current evaluator accepts paths and executes each once.

- [ ] **Step 4: Implement ordered execution**

For each selected case and attempt, call the producer once against the vulnerable tree and reuse its submitted differential probe for the remediated tree through the kernel contract. Do not generate a second fixed-side probe. Finalize every row even on provider, budget, build or infrastructure errors.

- [ ] **Step 5: Update Make variables and help**

Set `CORPUS_MANIFEST ?= benchmarks/dataset/manifest.json`, `EVAL_SET ?= development` and `ATTEMPTS ?= 1`; preserve `RUNS ?= .runs/lite`. Reject `ATTEMPTS < 1` and release runs with `--no-audit`. Record the manifest content hash while omitting private manifest paths from serialized run records.

- [ ] **Step 6: Verify and commit**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_eval.py -v`

```bash
git add src/corsair/cli.py src/corsair/evals.py Makefile tests/test_eval.py
git commit -m "feat: run independent manifest-selected eval attempts"
```

### Task 4: Implement the 80% policy and absolute release gates

**Files:**
- Create: `src/corsair/scoring.py`
- Create: `benchmarks/dataset/benchmark-policy.json`
- Modify: `src/corsair/cli.py`
- Modify: `tests/test_eval.py`

**Interfaces:**
- Produces: deterministic `score(run, manifest, policy) -> Scorecard` with overall, language, vulnerability type, framework and execution-mode strata.

- [ ] **Step 1: Write accuracy and confidence tests**

Cover 0/1, 4/5, 79/100, 80/100 and 100/100, exact numerators/denominators, family-weighted macro and case-level micro counts, and Wilson 95% intervals. First-attempt is the primary gate; success-within-three and attempt distribution are descriptive.

- [ ] **Step 2: Write graded-gate boundary tests**

An overall score below 80% fails. Each of Python, JavaScript, Java and Perl independently requires at least 80% and at least one qualified family. Vulnerability-type and framework strata become 80% gates at five independent families; smaller strata remain visible and informational.

- [ ] **Step 3: Write absolute-gate tests**

Fail on sandbox/authorization/oracle-leakage/evaluator-integrity events, a decisive false-safe vulnerable result, decisive false-exploitable remediated result, corpus/reference failure, incomplete language coverage, claimed integration without a case, infrastructure-incomplete scorecard or regression below the frozen policy tolerance.

- [ ] **Step 4: Verify the tests fail**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_eval.py -k 'accuracy or release or absolute or confidence' -v`

Expected: FAIL because current scoring requires 100% flat case agreement and has no strata.

- [ ] **Step 5: Implement deterministic scoring**

Match vulnerable disposition, remediated disposition or approved reason code, and fix status. Generic `INCONCLUSIVE` is incorrect. Treat missing/infrastructure rows as incomplete and release-blocking rather than dropping them from denominators. Calculate p50/p95 by a documented nearest-rank method.

- [ ] **Step 6: Create and freeze the policy only after baseline**

The policy starts with the approved 0.80 minimum and hard gates. After the first complete qualified-corpus live run, add dataset version, sample sizes, first-attempt overall/per-language baseline and any stricter regression floor in a dedicated commit made before prompt/skill tuning. A release run with an unfrozen policy is blocked.

- [ ] **Step 7: Verify and commit**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_eval.py -v`

```bash
git add src/corsair/scoring.py src/corsair/cli.py benchmarks/dataset/benchmark-policy.json tests/test_eval.py
git commit -m "feat: enforce multilingual 80 percent release gate"
```

### Task 5: Render scorecards and compare controlled model runs

**Files:**
- Create: `src/corsair/reporting.py`
- Modify: `src/corsair/cli.py`
- Modify: `Makefile`
- Modify: `tests/test_eval.py`

**Interfaces:**
- Produces: `scorecard.json`, `scorecard.md`, and `corsair compare-evals --baseline-run ... --candidate-run ...` / `make compare-evals`.

- [ ] **Step 1: Write report snapshot tests**

Require first-attempt accuracy, success within three, exact family counts, failure reasons, hard-gate ledger, p50/p95 latency, input/output/cached/reasoning tokens, total and per-attempt/per-success cost, and strata by language/CWE/framework/execution mode. Every failure row shows case/family, attempt, expected/observed pair, last gate/reason and redacted artifact link.

- [ ] **Step 2: Write comparison tests**

Accept two runs that differ only in provider/model configuration. Reject or prominently mark runs with different dataset, prompt, skill, policy, tool, image, kernel, budget, attempt or sampling hashes. Test different skill and image hashes explicitly.

- [ ] **Step 3: Verify the tests fail**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_eval.py -k 'report or compare' -v`

Expected: FAIL because neither renderer nor comparator exists.

- [ ] **Step 4: Implement concise JSON and Markdown reports**

Lead with pass/block status and exact failed gates. Show accuracy beside latency/tokens/cost for every model. Preserve `null` for unavailable metrics and show the pricing provenance for estimates.

- [ ] **Step 5: Implement deterministic comparison**

Report absolute and percentage-point accuracy changes plus latency/token/cost deltas overall and by stratum. Do not assign statistical significance when attempt counts are too small; always show numerator, denominator and confidence interval.

- [ ] **Step 6: Verify and commit**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_eval.py -v`

```bash
git add src/corsair/reporting.py src/corsair/cli.py Makefile tests/test_eval.py
git commit -m "feat: compare model quality latency and cost"
```

### Task 6: Wire CI evidence and document model experimentation

**Files:**
- Modify: `.github/workflows/development.yml`
- Modify: `README.md`
- Modify: `docs/design.md`
- Modify: `docs/readiness.md`
- Modify: `src/corsair/agent-contracts.yaml`
- Modify: `tests/test_contracts.py`

- [ ] **Step 1: Test command and status contracts**

Assert PR CI includes offline tests, `corpus-check` and one reference conformance replay. Assert corpus/kernel/adapter/image changes map to affected three-replay jobs. Live jobs must distinguish `passed`, `failed`, `blocked` and `unrun`; unavailable credentials/provider cannot become pass.

- [ ] **Step 2: Document controlled model configs**

Show how two versioned provider JSON files map producer and auditor independently, how to run identical `EVAL_SET`/`ATTEMPTS`/budgets, and how `compare-evals` checks comparability. Keep credentials in environment variables.

- [ ] **Step 3: Run deterministic verification**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache make test-offline`

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache make corpus-check`

Expected: PASS.

- [ ] **Step 4: Run or explicitly block live baseline evidence**

Run: `make eval EVAL_SET=release ATTEMPTS=3 PROVIDER=<approved-config>` when the provider is configured. Record exact passed/failed/blocked state; do not freeze a baseline from scripted models.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/development.yml README.md docs src/corsair/agent-contracts.yaml tests/test_contracts.py
git commit -m "docs: define repeatable model evaluation evidence"
```
