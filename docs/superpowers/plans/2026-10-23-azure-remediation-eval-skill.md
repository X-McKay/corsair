# Azure Remediation Evaluation Developer Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a developer skill that accepts closed Azure DevOps work-item IDs, pins each issue's own vulnerable commit and current remediation revision, runs the paired Corsair evaluation once, guides evidence-based improvement, and makes every corrected failure a durable private regression.

**Architecture:** A repository-local developer skill orchestrates read-only Azure DevOps queries, existing evaluator entry points and two small testable helper scripts. Resolution and private-registry mechanics are deterministic code; the skill owns judgment, diagnosis, replay order and promotion discipline. No public `corsair improve` command is added.

**Tech Stack:** Markdown agent skill, Python 3.12 helpers, Azure CLI/DevOps REST read-only commands, Pydantic, pytest, existing corpus/eval APIs.

**Spec:** `docs/superpowers/specs/2026-10-23-multilingual-benchmark-and-improvement-loop-design.md`

## Global Constraints

- Implement after the corpus and evaluation-metrics plans.
- Read and apply `superpowers:test-driven-development` and `superpowers:writing-skills` before Task 1.
- The skill lives only at `.agents/skills/azure-remediation-eval-loop/SKILL.md`; it must not enter `src/corsair/skills/`, model prompts or producer-visible mounts.
- Follow `superpowers:writing-skills`: establish failing no-skill baselines before writing `SKILL.md`, then rerun the same pressure scenarios with the skill.
- Azure DevOps access is read-only. Never update work items, comments, tags, branches, commits, pull requests or policies.
- Resolve each issue independently. There is no default remediation branch shared across the input list.
- Pin the remediation branch head once at run start and record both ref and SHA. Never evaluate a moving branch name without the pin.
- Use the originally attached vulnerable commit from immutable relation/update history. Do not infer it from the current default branch.
- If mapping is ambiguous, mark only that issue `NEEDS_MAPPING`, continue independent issues, then ask one consolidated mapping question.
- The baseline uses exactly one fresh end-to-end attempt per issue. Internal producer submissions remain bounded by the configured budget; automatic extra attempts cannot hide a first-pass failure.
- Expected outcomes come from reviewed source evidence and remain fixed during improvement. Never edit an oracle to make a change pass.
- A corrected failure is not accepted until deterministic reference and end-to-end regression tracks are promoted, related strata pass and the complete regression gate passes.
- Private issue IDs, source, findings and artifacts stay in the configured private registry or companion repository. Public Corsair receives no sensitive case material without explicit publication review.
- Credentials are environment-owned, never accepted on command lines and never written to artifacts.

## Review Focus

- Two issues with different branches must retain separate branch refs and SHAs; pin `test_resolver_has_no_global_remediation_branch` in Task 2.
- A deleted branch without an explicit linked merge commit must become `NEEDS_MAPPING`; pin this in Task 2.
- Every Azure command must be allowlisted read-only; pin `test_resolver_rejects_mutating_azure_commands` in Task 2.
- The initial baseline must set `ATTEMPTS=1`; pin this in Task 3.
- A failed case must be registered before system code changes; pin event ordering in `test_failure_is_registered_before_change` in Task 3.
- A focused pass without both regression tracks and three reference replays must remain `candidate`; pin this in Task 3.
- A prompt/skill change that improves one case but degrades a language or CWE stratum must be rejected; pin the scenario in Task 5.
- Public Git status must remain free of private issue identifiers and registry files; pin this in Task 6.

---

### Task 1: RED-test behavior without the developer skill

**Files:**
- Create: `tests/skills/azure-remediation-eval-loop/pressure-scenarios.md`
- Create: `tests/skills/azure-remediation-eval-loop/baseline-observations.md`
- Create: `tests/skills/azure-remediation-eval-loop/rubric.json`

**Interfaces:**
- Produces: repeatable scenarios and documented no-skill failures that determine the minimum useful skill content.

- [ ] **Step 1: Write pressure scenarios and rubric before the skill exists**

Include at least: (1) ten issues under time pressure with different remediation branches and two ambiguous links; (2) a costly failed baseline where changing the oracle would make it pass; (3) a focused improvement that regresses Java and a private case whose source must not be committed. Score revision provenance, read-only behavior, one-attempt baseline, ambiguity handling, diagnosis, replay scope, regression promotion and privacy.

- [ ] **Step 2: Run fresh subagents without the skill**

Use at least three independent runs per full pressure scenario, with the skill path absent from context. Capture verbatim choices and rationalizations, especially global-branch fallback, retrying until green, oracle changes, skipped promotion, Azure writes and public case leakage.

- [ ] **Step 3: Confirm there is a real baseline failure**

If no run violates the target behavior, stop and do not create redundant guidance. Otherwise record the smallest recurring failures the skill must correct.

- [ ] **Step 4: Commit only the RED evidence**

```bash
git add tests/skills/azure-remediation-eval-loop
git commit -m "test: capture remediation-loop skill failures"
```

### Task 2: Build the read-only per-issue revision resolver with TDD

**Files:**
- Create: `.agents/skills/azure-remediation-eval-loop/scripts/resolve-work-items.py`
- Create: `.agents/skills/azure-remediation-eval-loop/references/resolution-schema.json`
- Create: `tests/fixtures/azure-devops/`
- Create: `tests/test_azure_remediation_skill.py`

**Interfaces:**
- Consumes: work-item IDs plus organization/project workspace configuration and environment-owned Azure credentials.
- Produces: one `IssueResolution` per ID with `RESOLVED|NEEDS_MAPPING|NOT_REMEDIATED|ERROR`, repository, vulnerable SHA/evidence, remediation ref/pinned SHA/evidence and sanitized reason.

- [ ] **Step 1: Write resolver tests against sanitized Azure fixtures**

Cover development-link history, later relation edits, linked PR merge commits, active per-issue source branches, deleted branches, multiple repositories, equally plausible commits, missing/closed states and one independent issue succeeding while another needs mapping. Add `test_resolver_has_no_global_remediation_branch`.

- [ ] **Step 2: Write command-safety and secret tests**

Allow only Azure read operations such as work-item show/update-history reads, PR show, ref list/get and commit reads. Reject create/update/delete/comment/tag/complete/push verbs before subprocess execution. Assert PATs and authorization headers never enter argv, stdout, JSON or exception text.

- [ ] **Step 3: Verify the tests fail**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_azure_remediation_skill.py -k resolver -v`

Expected: FAIL because the helper does not exist.

- [ ] **Step 4: Implement deterministic resolution**

Invoke `az` with argument arrays and JSON output, never a shell string. Read the work item plus update/relation history, locate the original immutable development-link commit, follow explicit PR/commit/branch links, query the current branch head once, and emit the pinned result. A merged/deleted branch may use its explicitly linked merge commit; otherwise return `NEEDS_MAPPING` rather than defaulting to main/master.

- [ ] **Step 5: Batch ambiguity without blocking independent work**

The helper writes every result atomically and exits with a distinct partial-mapping status. It never prompts; the skill later presents one consolidated mapping table.

- [ ] **Step 6: Verify and commit**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_azure_remediation_skill.py -k resolver -v`

```bash
git add .agents/skills/azure-remediation-eval-loop/scripts .agents/skills/azure-remediation-eval-loop/references tests/fixtures/azure-devops tests/test_azure_remediation_skill.py
git commit -m "feat: resolve Azure remediation revisions read only"
```

### Task 3: Build private candidate registration and promotion mechanics

**Files:**
- Create: `.agents/skills/azure-remediation-eval-loop/scripts/register-regression.py`
- Create: `.agents/skills/azure-remediation-eval-loop/references/private-registry-schema.json`
- Modify: `.gitignore`
- Modify: `tests/test_azure_remediation_skill.py`

**Interfaces:**
- Uses: required `CORSAIR_PRIVATE_REGISTRY` outside the public repository and existing benchmark/eval schemas.
- Produces: immutable candidate/revision records, before/after run links and promotion status for deterministic-reference and end-to-end tracks.

- [ ] **Step 1: Write registry lifecycle tests**

Test `observed -> candidate -> corrected -> reference_qualified -> promoted`, exact vulnerable/remediated SHAs, fixed expectations, source visibility/retention, authorization review, deduplication, three reference receipts and technical review. Add `test_failure_is_registered_before_change` and reject skipping states.

- [ ] **Step 2: Write baseline invocation tests**

Given a resolved issue, generate a private manifest and case request whose vulnerable source is the historical SHA and fixed source is the pinned issue-specific remediation SHA. Invoke `corsair eval --manifest <private-manifest> --eval-set regression --attempts 1`; assert one differential probe is reused for both revisions, expected vulnerable `LIKELY_EXPLOITABLE`, and expected fixed `LIKELY_NOT_EXPLOITABLE` or one reviewed reason code such as `TARGET_REMOVED`.

- [ ] **Step 3: Write privacy tests**

Reject a registry located inside the public checkout unless it is an explicitly configured private companion worktree. Store hashes and sanitized aggregate metadata in public reports; never copy private source, issue descriptions, IDs, manifest paths or full source paths into the public corpus.

- [ ] **Step 4: Verify the tests fail**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_azure_remediation_skill.py -k 'registry or baseline or private' -v`

Expected: FAIL because the registry helper does not exist.

- [ ] **Step 5: Implement atomic registration and promotion**

Create records exclusively, append immutable lifecycle events, and require the pre-change failing run before accepting a system-change hash. Refreshing a remediation branch creates a new reviewed case revision; it never mutates prior evidence.

- [ ] **Step 6: Verify and commit**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_azure_remediation_skill.py -v`

```bash
git add .agents/skills/azure-remediation-eval-loop/scripts/register-regression.py .agents/skills/azure-remediation-eval-loop/references/private-registry-schema.json .gitignore tests/test_azure_remediation_skill.py
git commit -m "feat: register private remediation regressions"
```

### Task 4: GREEN-write the minimum developer skill

**Files:**
- Create: `.agents/skills/azure-remediation-eval-loop/SKILL.md`
- Modify: `tests/skills/azure-remediation-eval-loop/rubric.json`

**Interfaces:**
- Trigger description starts with `Use when...` and names closed/remediated Azure DevOps IDs, before/after security evaluation, failed-case diagnosis and regression promotion.

- [ ] **Step 1: Use the exact baseline failures to choose guidance form**

Use structural recipes for required output/order, explicit prohibitions for observed discipline failures, and observable conditionals for ambiguous mappings and removed targets. Do not add speculative sections unsupported by RED evidence.

- [ ] **Step 2: Write the workflow in reviewable stages**

The skill must perform: preflight and private-registry check; read-only per-issue resolution; consolidated ambiguity mapping; one-attempt baseline; failure registration; evidence-based diagnosis; smallest justified change; focused replay; related language/CWE/framework replay; full regression/release check; mandatory dual-track promotion; before/after comparison.

- [ ] **Step 3: Define the diagnostic decision table**

Classify source mapping, build/runtime, probe contract, target coverage, audit, disposition kernel, prompt/skill and provider behavior. Each class names the evidence to inspect and the focused replay to run. The skill must never propose a prompt change for a deterministic source/adapter failure.

- [ ] **Step 4: Define user-facing checkpoints**

Proceed automatically for unambiguous read-only mapping and local evaluation. Ask only for unresolved issue mappings or publication/other irreversible external actions, and batch those questions. Report provider unavailability as blocked evidence.

- [ ] **Step 5: Keep the skill concise and self-contained**

Use one complete example with two issues on different branches, one `TARGET_REMOVED` remediation and one corrected failure. Put Azure field details and registry schemas in `references/`; invoke scripts with `python`, not bare executable paths.

### Task 5: Verify the skill under the original and adversarial scenarios

**Files:**
- Modify: `.agents/skills/azure-remediation-eval-loop/SKILL.md`
- Create: `tests/skills/azure-remediation-eval-loop/green-observations.md`
- Modify: `tests/skills/azure-remediation-eval-loop/rubric.json`

- [ ] **Step 1: Micro-test wording against the no-skill control**

For each behavior-shaping passage, run at least five fresh-context samples with and without the skill. Read every scored response; require lower violations and lower variance before keeping the wording.

- [ ] **Step 2: Rerun the full RED pressure scenarios with the skill**

Use fresh subagents and the same inputs/rubric. Require correct per-issue branches, read-only Azure use, one-attempt baseline, no oracle edits, candidate registration before change, related/full replay and dual-track promotion.

- [ ] **Step 3: Add an explicit cross-stratum regression scenario**

A change fixes a Python traversal case but drops Java or CWE-22 below policy. The skilled agent must reject the improvement and continue diagnosis rather than promote it.

- [ ] **Step 4: Close observed loopholes and retest**

Record new rationalizations verbatim, add only guidance that addresses them, and repeat until every required behavior passes the rubric. Include a concise rationalization table and red-flags list for actual discipline failures.

- [ ] **Step 5: Commit the verified skill**

```bash
git add .agents/skills/azure-remediation-eval-loop tests/skills/azure-remediation-eval-loop
git commit -m "docs: add tested Azure remediation eval skill"
```

### Task 6: Exercise one full synthetic improvement loop

**Files:**
- Create: `tests/fixtures/azure-devops/full-loop/`
- Modify: `tests/test_azure_remediation_skill.py`
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `docs/readiness.md`

- [ ] **Step 1: Build a sanitized end-to-end fixture**

Use two work items in different repositories/branches: one decisive secure remediation and one reviewed removed-target remediation. Make the first model attempt fail for a known deterministic reason, then represent a corrected system revision.

- [ ] **Step 2: Run the complete lifecycle with fakes for external services only**

Verify resolution, pinned revisions, one-attempt before run, candidate registration, diagnosis, focused and related-strata replays, complete regression scoring, three reference replays and end-to-end promotion. Assert pre-change evidence remains immutable.

- [ ] **Step 3: Prove the public boundary**

Add `test_public_tree_contains_no_private_issue_ids`, inspect `git status --short`, and assert run/report redaction. Confirm `corsair --help` has no `improve` command.

- [ ] **Step 4: Document developer discovery**

Add a short `AGENTS.md` trigger pointing to the skill. Document required Azure organization/project configuration, `CORSAIR_PRIVATE_REGISTRY`, provider config, read-only credentials and blocked states without duplicating the workflow.

- [ ] **Step 5: Run deterministic verification**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_azure_remediation_skill.py tests/test_contracts.py -v`

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache make test-offline`

Expected: PASS with no network or live model requirement.

- [ ] **Step 6: Record live evidence separately**

When authorized Azure and model credentials are configured, run the skill on reviewed non-sensitive test issues. Record `passed`, `failed` or `blocked`; do not treat the synthetic fixture as proof of live Azure mappings or model quality.

- [ ] **Step 7: Commit**

```bash
git add tests/fixtures/azure-devops tests/test_azure_remediation_skill.py AGENTS.md README.md docs/readiness.md
git commit -m "test: verify the remediation improvement loop"
```
