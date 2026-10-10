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

## Using the skills

Launch the client from the repository. Codex supports repository `.agents/skills` and follows symlinked skill folders; Claude uses real project folders in `.claude/skills`. Preserve Git symlinks when cloning. Do not copy and independently edit a second skill set.

| Task | Codex explicit invocation | Claude Code explicit invocation |
| --- | --- | --- |
| Plan/implement/resume | `$corsair-development` | `/corsair-development` |
| Review design/code/evidence | `$corsair-review` | `/corsair-review` |
| Prepare continuation | `$corsair-handoff` | `/corsair-handoff` |

Clients can also select skills from their descriptions. If an already-running session does not discover newly added skills, start a fresh session or explicitly read the `SKILL.md` file. Missing symlink support should be fixed in the checkout, not by maintaining duplicated instructions. Claude imports `AGENTS.md` through `@AGENTS.md`; Codex reads it natively.

`make test-config` checks skill metadata/links, record formats, cross-references and local documentation links alongside existing offline guards. The native GitHub Actions development workflow runs these offline checks on PRs and main pushes, without deployment, provider calls or live runtime qualification. The PR template asks for changed records, measured validation and remaining limits. Instructions guide behavior; these structural checks do not prove a model follows the workflow. Native skill discovery/invocation and agent behavior still need smoke checks in the actual client.

References: [Codex skills and symlink discovery](https://developers.openai.com/codex/skills/), [Codex repository instructions](https://developers.openai.com/codex/guides/agents-md/), [Claude Code skills](https://code.claude.com/docs/en/skills), [Claude memory/imports](https://code.claude.com/docs/en/memory), [Anthropic skill examples](https://github.com/anthropics/skills).
