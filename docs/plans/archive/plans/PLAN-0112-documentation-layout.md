---
id: PLAN-0112
kind: plan
title: Align project documentation with the requested hierarchy
status: implemented
updated: 2026-10-25
---

# Documentation hierarchy

Scope is documentation only: root navigation/contribution/security/changelog/license-status files; docs index; getting-started, architecture/decisions, development, guides, operations/runbooks, reference and agent guides; active/archived plans and attributable historical evidence. No runtime, prompt, configuration, permissions, workflow or scoring changes are authorized by this documentation task.

Preserve all existing dirty work on manus/just. Source/resource hashes are checkpointed before the move. Consolidate current guidance, avoid duplicate authorities and placeholder pages, and retain earlier failed/unrun results and policy/security limits. No license currently exists; preserve that legal state rather than silently selecting a license. No release or deployment is implied.

Seven bounded documentation owners write independent sections. Parent owns root navigation, plans/archive migration, link integrity, command/API/configuration/schema conformance and delivery. Run documented non-destructive commands, test affected package/CLI/Just boundaries, perform a final cleanup, retest and package the final working tree excluding credentials, runs, caches, git metadata and raw diagnostics. Full live model evaluation is not repeated for prose-only changes; retain its real 2/3 result and open safe-case issue. Build and check the final archive, not a stale git-HEAD-only export.


## Actual results

Implemented the requested root files and all documentation sections, including three real ADRs, current source-backed references and the actual pilot runbook. Retained27 moved documents and their historical qualification context; repaired their relative links. No runtime/resource file changed (62 file hashes verified). No project-wide license grant was present, so LICENSE explicitly records the unlicensed status rather than choosing new terms.

Before final cleanup: locked Just/Ruff/ty checks passed and103 offline tests passed (31 native/live tests deselected) in35.41s. After cleanup: all quality gates passed again;103 offline tests passed in19.07s,31 deselected, warnings as errors. Fresh sdist/wheel build succeeded with the pre-existing uv/uv-build version-range warning; pins were not changed. CLI help for10 entrypoints,9 parser examples,19 settings/model fields,5 canonical JSON schemas and all documented Corsair imports were checked without starting services. The completed hierarchy had45 required pages,398 checked local links,11 Python blocks and82 shell blocks before final handoff/index links were added; final counts are in the documentation receipt.

Actual Docker/Temporal/live evaluation was not rerun for prose-only changes. No provider configuration was accessed, no new service was started, and no target/model call was made by this migration. Earlier134-test runtime and2/3 live-batch receipts remain historical evidence with an explicit open safe-case issue. A cached Nix invocation initially lacked daemon-socket IPC permission; the same offline checks passed with only the required existing-daemon access. Initial missing cross-links during independent writing and a system-Python3.9/Python3.12 grammar mismatch were resolved before final verification.

Final delivery packages the actual current working tree, including earlier uncommitted implementation work, with checksums and without .git, credentials, caches, raw runs, private settings or diagnostics. Branch remains manus/just, previous main stash unchanged; no commit/push/merge/deployment or release was performed. See HANDOFF-0144 for delivery details.
