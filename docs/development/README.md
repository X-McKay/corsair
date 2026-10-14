# Development workflow

For iterative corpus evaluation and per-language accuracy baselines, follow the [corpus improvement loop](../runbooks/corpus-improvement-loop.md) and its repository-owned kickoff records.

Start each session with [AGENTS.md](../../AGENTS.md) and [CURRENT.md](CURRENT.md). The rulebook holds shared principles; this guide holds the process. Codex and Claude use the same records, definitions and skills. There is no separate tracker database, custom workflow service or required approval ceremony.

## Repository locations

| Content | Canonical location | Purpose |
| --- | --- | --- |
| Shared agent instructions | `AGENTS.md` | Always-read development principles and session routine |
| Claude entry point | `CLAUDE.md` | Native import of the shared instructions |
| Skill source | `.claude/skills/<name>/SKILL.md` | One copy of development, review and handoff instructions |
| Codex discovery | `.agents/skills/<name>` | Git symlinks to the canonical skill folders |
| Current work | `docs/development/CURRENT.md` | Short index of active plan, blockers and latest handoff |
| Ideas | `docs/development/ideas/IDEA-NNNN-<slug>.md` | Proposed/deferred opportunities; no implicit scope approval |
| Specs | `docs/development/specs/SPEC-NNNN-<slug>.md` | Goal, boundaries, observable behavior and acceptance |
| Implementation plans | `docs/development/plans/PLAN-NNNN-<slug>.md` | Ordered small steps, validation, decisions and progress |
| Development issues | `docs/development/issues/ISSUE-NNNN-<slug>.md` | Reproducible defects/blockers and resolution criteria |
| Handoff snapshots | `docs/development/handoffs/HANDOFF-NNNN-<slug>.md` | Verified state and copyable next-session prompt |
| Templates | `docs/development/templates/` | One native Markdown template per record type |
| Accepted system design | Existing `docs/` contracts/architecture | Authoritative design; specs link to it rather than duplicate it |
| Qualification/runbooks | `docs/qualification/`, `docs/runbooks/` | Reviewed coverage and operational procedures |
| Raw evidence/private state | `.runs/`, `.state/` | Ignored runtime evidence and separate credentials/ownership |

Repository issue records are development work, distinct from the security findings Corsair will ingest. If a GitHub/Azure issue is used, add its URL to the record and treat it as a linked discussion; do not maintain two competing status sources. Publishing/closing external issues is a separate authorized action. A PR links the record IDs and uses the native PR template.

## Standard record format

Copy the relevant template. Each record has YAML frontmatter: `id`, `kind`, `title`, `status`, `updated` (ISO date), and `related` (list of repository record IDs). Use the next unused number in that type and a lowercase hyphenated slug. The filename starts with the record ID, and its main heading matches the metadata title. Keep IDs stable; check for collisions before adding a record. Update `updated` when a living record changes. Handoffs are snapshots; append a new handoff rather than rewriting previous session facts.

| Kind | Status vocabulary | Meaning |
| --- | --- | --- |
| idea | proposed, accepted, deferred, rejected | Accepted means selected for specification, not implemented |
| spec | draft, accepted, superseded | Accepted means agreed behavior/scope, not runtime qualification |
| plan | draft, ready, in_progress, blocked, complete, cancelled | Complete means its scoped deliverables/checks are accounted for; explicit qualification limits remain |
| issue | open, in_progress, blocked, resolved, wont_fix | Resolve only when its stated resolution criteria have evidence |
| handoff | recorded | Historical snapshot; `CURRENT.md` identifies the latest one |

An issue can stay open while its dependent plan is blocked. A template, render, mock or version command is never live qualification. Record `passed`, `failed`, `blocked`, `unsupported` and `unrun` checks explicitly; possible remote completion stays `unknown`. Link reviewed qualification reports separately from implementation status.

## Session workflow

1. **Resume:** Inspect git/source state, current work and relevant handoff. Verify the current gate and reconcile stale records before proceeding.
2. **Scope:** Choose one bounded objective. Capture an idea if useful, a spec for substantial behavior/boundary changes, and a plan for nontrivial implementation. For a small correction, update an existing plan/issue; do not create all five record types automatically.
3. **Design:** Prefer upstream features. Name contract/authority/mode changes, observable failure layers and relevant evaluation dimensions. Record material tradeoffs in the spec/plan. User direction and existing authorization establish scope; `accepted`/`ready` do not force another confirmation round.
4. **Build:** Implement one independently testable component. Update steps/decisions as evidence changes. A blocked prerequisite prevents dependent integration but does not prevent independent research, docs or fixes.
5. **Validate and review:** Run the smallest meaningful suite, then affected consumers and necessary live/durable/agent evaluations. Apply the review skill; retain failed attempts, actual coverage and unknowns.
6. **Record and hand off:** Update the living records/current index, add a handoff snapshot, and report actual outcome/next steps. Commit and publish according to user authorization. Existing design docs remain the architectural source of truth.

## Maintain the unit-test approach

For new and ongoing investigation work, follow the [investigation contract](../investigation-contract.md): exactly the benign control and security regression through existing real application seams. The shared observation and validity contracts apply across languages, frameworks and CWEs. Native adapters handle discovery, execution and reporting; do not introduce per-CWE verdict logic or mandatory language-specific recorders.

The current six roles are environment, identification, planning, independent control authoring, independent exploit authoring and assessment. Each author has its own specification, identity/path, context, budget and provider key, source reads and one approved file write. It drafts source-only test code and assertion anchors; execution belongs to deterministic nodes after a separate outcome-blind validity call. Preserve a simple ordinary benign control and a true reported-condition adversarial safety test across languages/frameworks/CWEs. Do not add peer draft context, author self-review, per-CWE branching or mandatory low-level recorders. [SPEC-0079](specs/SPEC-0079-independent-probe-authoring.md) tracks the production transition; retained joint-author evals are historical comparisons.

Every investigation change explains the measured property, actual source target, assertion, dependency-double boundary and independent validity evidence. Review both a valid native test and a relevant invalid case, such as a substituted implementation, irrelevant assertion or a double that supplies the safety guard. If integration is needed, record which part of the property cannot be established at the unit seam and retain that scope in the report. Keep passing test claims distinct from an outcome-blind review of frozen tests before execution. The later disposition call consumes the source/plan/patch-bound review without changing it. Both probes still require actual native outcomes on every revision; matching observation kinds or a revision differential alone cannot establish validity. Existing witness implementations are compatibility/supporting paths, not a template for new investigation requirements.

Carry these decisions into active plans and handoffs when work resumes. The development, review, scaffold and base-image skills and PR checklist use this same contract. A documentation or prompt change is not proof of live model behavior; compare the affected agent evaluations and record qualification limits.

## Isolated agent evaluation

Each agent is improved through its own loop, independent of the cluster and of other workstreams ([SPEC-0044](specs/SPEC-0044-isolated-agent-evaluation.md)):

1. **Eval set:** frozen typed stage inputs with evaluator-only oracles under `evals/<stage>/`; held-out sets beside the development set, frozen by manifest and never named in records (SPEC-0023).
2. **One command:** `make eval AGENT=<environment|identification|planning|control_authoring|exploit_authoring|assessment|chain> [SET=…] [PROVIDER_CONFIG=<providers.json>] [REPEAT=…] [NOTE="what changed"]`. Without `PROVIDER_CONFIG` it runs scripted; with it, live against the selected per-agent model profile (legacy shared vLLM files remain supported; see [provider configuration](../runbooks/provider-configuration.md)).
3. **Results:** `.runs/evals/<agent>/<UTC stamp>-<set>-<mode>/` holds `command.json`, the suite's `evidence/`, `summary.json` (prompt/config/skill versions, model, dataset digest, pass rates, efficiency) and `comparison.md` against the promoted baseline or else the previous run; `index.jsonl` lists every run. Promote a reference with `make eval-baseline AGENT=<name> RUN=<run id>`.
4. **No cluster:** sandboxes, runners and command executors are ports answered by fixtures, recorded observations or deterministic host doubles. Model-written code is never executed on the host; the authoring eval uses a static host runner and leaves execution dimensions unknown until a sandbox replay.

A change to an agent states the baseline it was compared with and the comparison's result in its plan. A new agent ships with its eval set and a `SUITES` entry in `evals/run.py`. Agent packages follow the [agent package convention](../agent-packages.md); a suite that reports `toolset_sha256` makes any change to the offered tools visible in `comparison.md`.

Walk stage baselines in execution order: environment, identification, planning, control authoring, exploit authoring, source-only validity, native execution, result assessment and deterministic disposition. Score assessment validity and interpretation calls separately; injected host observations do not qualify native execution. Preserve frozen sets and version new multilingual coverage.

For the versioned multilingual staged suite, use a fresh evidence directory for each role:

```shell
PYTHONPATH=src:. <repository-runtime-python> -m evals.experiments.staged_baseline.evaluate --agent planning --evidence <fresh-evidence-directory> --provider-config <providers.json> --repeat 1
```

Supported staged `--agent` values are `identification`, `planning`, `control_authoring`, `exploit_authoring` and `validity`; validity selects the assessment provider key. Omit `--provider-config` for native FunctionModel fixture plumbing. Environment uses its own isolated evaluator, including `make eval AGENT=environment SET=development-v2`. The staged runner currently supports one repeat; record that limit instead of presenting a consistency result. Source-only projections are available through `python -m evals.experiments.staged_baseline.cases --stage <environment|identification|planning|validity>`; exported operator metadata must stay outside model inputs.

Author evaluator success establishes contract/draft admission only: confined own-file writes, source-read coverage, assertion-anchor bounds and typed completion. Review the actual generated source pair separately for production binding, benign/adversarial inputs, asserted properties and dependency substitutions before claiming semantic validity. Native execution is a further boundary; unavailable native ports/outcomes remain unknown or unqualified, never zero failures. Report configured and effective input-derived budgets/output retries: factory reuse alone does not make measurements with different caps comparable.

## Live qualification

While Corsair is in active development (Al, 2026-10-13 13:55Z), toolchain work does not wait on RIG0. A toolchain, runner or harness PR is proven under plain Docker and lands with its matrix row marked `evidence: image-only`; the detector selects that row, so cases and evals can use the runtime at once. The kind/OpenShell gate runs once per milestone, when Al chooses one: one self-contained paste, one fresh cluster, the gate (and case target, where one exists) for every image changed since the last batch, then one small PR that upgrades those rows to `evidence: live`. Only a live row counts as qualified in reports and records. Changes to sandbox, policy or gateway code still pass the gate before they merge.

Live runs use the shared RIG0 host and its one kind cluster, so they come last and cost the most. Three tiers keep most checks off it ([SPEC-0062](specs/SPEC-0062-live-qualification-tooling.md)):

| Tier | Where | Use it for | Command |
| --- | --- | --- | --- |
| Offline | Cloud, CI or any host | Every change. `make test-config` includes stub smoke runs of each live harness up to its first native command, so wiring bugs (a missing evidence directory, a gateway consumed by the first of several gates, an unresolved fixture, a CLI that does not parse) fail here, not on RIG0. They qualify nothing | `make test-config` |
| Image-only | Docker on a host, no cluster | Toolchain, runner and harness changes: build the image (its trusted control runs offline in the container), run the gate body under `docker exec`, and run one real case through the runner and image-case harness at the vulnerable and fix commits. The `Toolchain images (image-only)` workflow builds the named images and runs their trusted controls; since 2026-10-14 it runs only on manual dispatch (gates deferred until end-to-end runs and agent baselines exist). A PR adds its real case to that job as a step guarded on its image directory, through the shared harness `tests/qualification/image_case.py`. Enough for an `evidence: image-only` row in the same PR; never sandbox evidence | `make toolchain-images TOOLCHAINS=<dir>`, then the case harness (for Maven, `tests.qualification.java_image_case` with the prepared image config id and clean case checkouts) |
| Kind/OpenShell gate | RIG0, this checkout's own cluster | Changes to sandbox, policy or gateway code, and the milestone batch that upgrades image-only rows to live | `make qualify-image TOOLCHAIN=<dir> [CASE=<id>]` |

`make qualify-image` runs the whole chain and stops at the first failure: tools, the cluster (created only when this checkout holds no receipt; it refuses to adopt one another checkout holds), admission and network (reused while the installer's and policy gate's own checks still accept an earlier run of this checkout on the same node and runtime lock, otherwise run fresh), image build (skipped when the prepared receipt matches the sources) and load, gateway install, the toolchain gate, then a fresh gateway and the image's `qualify-<dir>-case` target when `CASE` is given. Each step logs under `.runs/qualify/<run>/logs/`, the gate and case keep their own evidence directories, and `SUMMARY.md` there is what a RIG0 session reports. It never runs `workspace-storage` or `kind-down`, never deletes retained state and never retries. `make cluster-status` answers who holds the cluster and what can be reused, read-only. `make archive-runs` copies a worktree's `.runs` into the main checkout's `.runs/worktrees/` and checks the copy; it removes nothing.

Rules for every live run:

- **One paste per run.** A RIG0 paste is self-contained, runs the branch head or a frozen commit, names the worktree `/home/al/git/corsair/.worktrees/<branch>` and its `.runs`, and is written once. `git worktree add` may need Al's hand or the allow rules in [deploy/rig0/settings.local.json](../../deploy/rig0/settings.local.json), which Al reviews once and merges into RIG0's `.claude/settings.local.json`. The pre-bash hook's blocks (`mkfs.`, `dd if=`, `kubectl delete namespace`, `kubectl delete --all`, `rm -rf /`) stay, and the file denies the same strings: hook-blocked commands never appear on a Claude Bash line, while the harness's own UID-guarded namespace cleanup runs inside the make targets, as it always has. The pre-allowed targets refuse to run with any other make goal, accept only an existing image directory as `TOOLCHAIN`, and pass every other value through the environment.
- **Row with the image, live later.** An image or runner PR adds its matrix row with `evidence: image-only` once the image-only tier passed and offline review and CI are clean. No row is marked `live` before a passed gate; the milestone batch's evidence goes in one small PR that flips the rows it covers.
- **A live pass counts only on the final source.** The gate records the source hashes it ran; a later change to any of them (including a merge that touches the gate harness) needs a rerun before the row lands. This is why a harness change merged into an image branch after its run costs one more RIG0 run (#51 after #55's merge), and why merging main into an image branch before its gate is cheaper than after.

Standing decisions a worker does not stop to ask about:

1. A replayed third-party proof test gets a Corsair-authored control copied verbatim from an unrelated upstream test in the same project, and the proof test stays byte-identical to its source.
2. Qualification evidence lives in each checkout's own `.runs` (the gateway installer and network check accept proof only from the checkout doing the install) and is archived with `make archive-runs` before a worktree is deleted.
3. A worker may tear down and recreate the cluster when it is idle and the worker holds it (its receipt is in the worker's checkout). Handover to another checkout is by message, and the next holder runs `make kind-down` in the previous holder's checkout.
4. A diagnosed failure that ran no test (a collection or harness error) may run once more after the fix, recorded as its own attempt. Blind retries stay forbidden.

## Using the skills

Launch the client from the repository. Codex supports repository `.agents/skills` and follows symlinked skill folders; Claude uses real project folders in `.claude/skills`. Preserve Git symlinks when cloning. Do not copy and independently edit a second skill set.

| Task | Codex explicit invocation | Claude Code explicit invocation |
| --- | --- | --- |
| Plan/implement/resume | `$corsair-development` | `/corsair-development` |
| Review design/code/evidence | `$corsair-review` | `/corsair-review` |
| Prepare continuation | `$corsair-handoff` | `/corsair-handoff` |
| Add or register a toolchain base image | `$corsair-base-image` | `/corsair-base-image` |
| Create an agent, add a tool, or move a package to the [convention](../agent-packages.md) | `$corsair-agent-scaffold` | `/corsair-agent-scaffold` |

Clients can also select skills from their descriptions. If an already-running session does not discover newly added skills, start a fresh session or explicitly read the `SKILL.md` file. Missing symlink support should be fixed in the checkout, not by maintaining duplicated instructions. Claude imports `AGENTS.md` through `@AGENTS.md`; Codex reads it natively.

`make test-config` checks skill metadata/links, record formats, cross-references and local documentation links alongside existing offline guards, adapter unit suites, native Temporal activity contracts and PydanticAI fixture/evaluation tests. The native GitHub Actions development workflow runs these offline checks on PRs and on pushes to main and develop, split over three parallel `offline-shard` jobs (`TEST_SHARD=k/n make test-config` runs one shard locally) beside `make test-v2`; the `offline-guards` check passes only when all of them do. It has no deployment, provider calls or live runtime qualification. Make honors a supplied `UV_CACHE_DIR` (including setup-uv's native cache); otherwise it defaults to the ignored repository cache. Live CI status/history is maintained by [GitHub Actions](https://github.com/X-McKay/corsair/actions/workflows/development.yml), not a second status ledger. The PR template asks for changed records, measured validation and remaining limits. Instructions guide behavior; these structural checks do not prove a model follows the workflow. Native skill discovery/invocation and agent behavior still need smoke checks in the actual client.

References: [Codex skills and symlink discovery](https://developers.openai.com/codex/skills/), [Codex repository instructions](https://developers.openai.com/codex/guides/agents-md/), [Claude Code skills](https://code.claude.com/docs/en/skills), [Claude memory/imports](https://code.claude.com/docs/en/memory), [Anthropic skill examples](https://github.com/anthropics/skills).
