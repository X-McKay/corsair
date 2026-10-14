# Development workflow

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
| Accepted system design | `docs/development/specs/SPEC-0082-corsair-v2-architecture.md`, mirrored in full at `docs/design/` | Authoritative v2 design; records link to it rather than duplicate it |
| Qualification | `docs/qualification/` | Reviewed toolchain coverage; v1 reports and runbooks remain on main |
| Runbooks | `docs/runbooks/` | Operator procedures on develop, such as the [OpenShell v2 cluster](../runbooks/openshell-v2.md) |
| Raw evidence/private state | `.runs/`, `.state/` | Ignored runtime evidence and separate credentials/ownership |

Repository issue records are development work, distinct from the security findings Corsair will ingest. If a GitHub/Azure issue is used, add its URL to the record and treat it as a linked discussion; do not maintain two competing status sources. Publishing/closing external issues is a separate authorized action. A PR links the record IDs and uses the native PR template.

## Standard record format

Copy the relevant template. Each record has YAML frontmatter: `id`, `kind`, `title`, `status`, `updated` (ISO date), and `related` (list of repository record IDs). Use the next number above the highest used in that type on main or develop (develop's numbering has gaps after the v2 clean-up; never reuse or renumber) and a lowercase hyphenated slug. The filename starts with the record ID, and its main heading matches the metadata title. Keep IDs stable; check for collisions before adding a record. Update `updated` when a living record changes. Handoffs are snapshots; append a new handoff rather than rewriting previous session facts.

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
6. **Record and hand off:** Update the living records/current index, add a handoff snapshot, and report actual outcome/next steps. Commit and publish according to user authorization. SPEC-0082 remains the architectural source of truth.

## Maintain the unit-test approach

[SPEC-0082](specs/SPEC-0082-corsair-v2-architecture.md) defines the probe protocol: exactly two native tests, a benign control and a proof-of-vulnerability (PoV) test that passes when it demonstrates the reported condition, written by the Control Prober and Exploit Prober through the real application seam, frozen, reviewed outcome-blind, then run once by trusted code. The outcome comes from the exit-code map, the marker files and the token, never from parsing reports. Framework knowledge lives only in matrix rows and framework skills; the chain never branches on language, CWE or case.

## Isolated agent evaluation

Each agent is improved through its own loop on the host, without a cluster (SPEC-0082, "Runs, evals and benchmarks: one layout"):

1. **Eval set:** frozen cases under `src/corsair/v2/agents/<name>/evals/<language>/<set>/<case-id>/` as `input.json`, `oracle.json` (evaluator-only) and `case.json`; chain cases under `evals/e2e/<language>/<set>/<case-id>/`. Held-out sets are frozen by manifest and never named in records.
2. **One command:** `make eval AGENT=<name> SET=<set> EVAL_LANGUAGE=<language> REPEAT=<n> [PROVIDER_CONFIG=<path>] [NOTE=<text>]`. The runner currently distinguishes scripted (no provider) and provider-enabled `live`; it has no `LANG` or `MODE` Make variable. See the [current evaluator layout/commands](../../evals/README.md) rather than inferring mode from a folder or name.
3. **Results:** the runner prints its evidence path; `summary.json`, `comparison.md`, `policy.json` and native attempt receipts retain input/release identity and null telemetry. Completion/evaluator coverage is separate from conditional semantic quality. A policy outside its declared set/mode is `not_applicable`. Optional `hard_gates.completion_rate` and `hard_gates.evaluator_failures` do not enable or promote policies by themselves.
4. **Qualification:** isolated fixture/recorded ports are legitimate model-development tools, not native workspace evidence. The current Builder provider-enabled scorer still uses recorded command observations. Keep that cohort separate from real-workspace and whole-chain qualification; no live baseline is implied by a scripted pass. Replay/native-workspace/cohort labeling remains tracked by the current plans.

Use the existing serial `make eval-live-baselines PROVIDER_CONFIG=<path>` helper rather than a second loop. Promotion requires a live whole-set run with recorded attempts; `make baseline-commit AGENT=<name> RUN=<id>` writes the selected snapshot under the agent's `evals/baselines/<set>-<mode>.json` (chain: `evals/e2e/baselines/`). These commands neither promote this audit's scripted runs nor prove native workspace qualification.

A change to an agent states the baseline it was compared with and the result in its plan. A new agent ships with its eval set, a scripted suite and a replay or live suite.

## Live qualification

Gates are deferred (Al, 2026-10-14) until at least three end-to-end runs reach the correct label in at least three languages and every agent has a baseline. Until then a toolchain or runner change is proven under plain Docker and lands with its matrix row marked `evidence: image-only`; no row is marked `live` without a passed kind/OpenShell gate on RIG0. The milestone gate, its RIG0 procedure and its standing decisions are on main (SPEC-0062 and the v1 development guide) and return with the gates.

Rules for every RIG0 run: one self-contained paste per run in a worktree under `/home/al/git/corsair/.worktrees/<branch>`; the hook-blocked commands never appear on a Claude Bash line; a live pass counts only on the final source; blind retries stay forbidden.

## Using the skills

Launch the client from the repository. Codex supports repository `.agents/skills` and follows symlinked skill folders; Claude uses real project folders in `.claude/skills`. Preserve Git symlinks when cloning. Do not copy and independently edit a second skill set.

| Task | Codex explicit invocation | Claude Code explicit invocation |
| --- | --- | --- |
| Plan/implement/resume | `$corsair-development` | `/corsair-development` |
| Review design/code/evidence | `$corsair-review` | `/corsair-review` |
| Prepare continuation | `$corsair-handoff` | `/corsair-handoff` |
| Add or register a toolchain base image | `$corsair-base-image` | `/corsair-base-image` |
| Create an agent, add a tool, or move a package to the convention | `$corsair-agent-scaffold` | `/corsair-agent-scaffold` |

Clients can also select skills from their descriptions. If an already-running session does not discover newly added skills, start a fresh session or explicitly read the `SKILL.md` file. Missing symlink support should be fixed in the checkout, not by maintaining duplicated instructions. Claude imports `AGENTS.md` through `@AGENTS.md`; Codex reads it natively.

Until something runs end to end (Al, 2026-10-14) the PR check `offline-guards` runs only `make test-v2`; the record, link and skill guards in `tests/configuration/test_development_workflow.py` run by hand with pytest. Full CI, gates and release policies return after end-to-end runs and agent baselines exist. Live CI status is in [GitHub Actions](https://github.com/X-McKay/corsair/actions/workflows/development.yml). Instructions guide behavior; these structural checks do not prove a model follows the workflow.

References: [Codex skills and symlink discovery](https://developers.openai.com/codex/skills/), [Codex repository instructions](https://developers.openai.com/codex/guides/agents-md/), [Claude Code skills](https://code.claude.com/docs/en/skills), [Claude memory/imports](https://code.claude.com/docs/en/memory), [Anthropic skill examples](https://github.com/anthropics/skills).
