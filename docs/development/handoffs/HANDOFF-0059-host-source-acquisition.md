---
id: HANDOFF-0059
kind: handoff
title: Host acquisition of exact benchmark commits
status: recorded
updated: 2026-10-13
related: [SPEC-0037, PLAN-0041, SPEC-0012, SPEC-0025, PLAN-0021]
---

# Host acquisition of exact benchmark commits

## Verified state

Branch `claude/benchmark-repo-fetch-g6cnts` from main `334aa03`. Delivered under [SPEC-0037](../specs/SPEC-0037-host-source-acquisition.md) and [PLAN-0041](../plans/PLAN-0041-host-source-acquisition.md):

- `src/corsair/adapters/git_acquire.py`: `GitAcquisition.acquire(FetchTarget, destination, operation)` fetches one exact commit over HTTPS (complete ancestry by default, explicit depth for measure-only) into a new private bare repository with a rebuilt Git environment and operator-named proxy/CA, verifies ref, commit hash, shallowness and `fsck --strict`, measures the commit and first parent (`TreeStats`), writes intent/result receipts with layered failures, and returns `AcquiredSource`, whose `target()` gives the SPEC-0025 `FetchTarget`. Opt-in `fsck_warn` downgrades only three format-only fsck messages and records them.
- `evals/benchmark/sources.py`: resolves all 50 inventory rows (commit, `.patch`, GitLab and pull-request commit URLs) and runs acquisition plus unchanged `GitSource` capture; `benchmarks/source-pins.json` holds one record per resolved case and the unresolved reasons.
- Tests: `tests/unit/test_git_acquire.py` (11), `tests/configuration/test_benchmark_sources.py` (2), two new capture tests in `tests/unit/test_artifacts.py`.
- `GitSource` (SPEC-0012) gained default-off `fsck_ignore` (three format-only ids) and `skip_nonregular` (symlinks and submodule links left out and listed in the manifest), reads blob sizes from one tree listing, and has higher operator ceilings (65,536 files, 256 MiB, 600 s).

It does not depend on or edit the files of draft PR #39 (case loader, IDEA-0005); it reads the inventory directly and can switch to that loader after both merge.

## Validation and blockers

- `make test-config`: 866 passed (853 on main plus 13 new).
- Network runs (ignored evidence under `.runs/acquire-20261013*`; PLAN-0041 has each): 40 of 50 cases resolve to a commit and all 40 are acquired with verified commits. 39 came from this cloud container. CVE-2023-31486 came from RIG0, because the container's egress proxy refuses salsa.debian.org. Six repositories need the opt-in format-only fsck allowance.
- `GitSource` captured all 40 fix commits and all 34 single parents. Seven entries were skipped and listed: cookiecutter doc symlinks, GitPython's `gitdb` submodule and one rails fixture symlink. The first capture run, at the old ceilings, refused 11; it is kept in PLAN-0041.
- The cases needing review are listed in PLAN-0041: 10 without a fix reference, 6 merge-commit fixes, 2 repository mismatches and 1 skipped submodule.
- Not run: the SPEC-0025 sandbox fetch (blocked on the storage quota, SPEC-0036 on PR #39), any build, test or case admission. Merge-commit fixes (6 cases) have no single-parent baseline candidate. Whether a first parent is the vulnerable revision is unverified for every case.

## Decisions and next steps

Settled here: complete ancestry by default so the qualified `GitSource` can capture; fetch from the repository named in the fix reference and flag inventory disagreement; format-only fsck downgrade is opt-in, three ids, recorded; repositories and captured objects are deleted after a run unless `--keep`. The SPEC-0025 sandbox recipe now skips and reports the same entries (default off) and admission matches them against the snapshot; `make test-config` 870 passed. Next: the sandbox fetch live once storage is qualified; whole-repository source tools (PR #40) consume these snapshots. Case review (Al) settles the lists in PLAN-0041.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then SPEC-0037, PLAN-0041 and this handoff. Inspect git/source state and verify recorded facts against benchmarks/source-pins.json. Use the Corsair development skill. Next bounded action: once the SPEC-0036 storage quota is qualified, run the SPEC-0025 sandbox fetch live for JSPWiki and one case with skipped entries (cookiecutter), comparing against the host captures. Do not weaken fsck beyond the three named message ids or treat a first parent as the vulnerable revision without case admission. Run make test-config, preserve evidence under .runs/, update the records and CURRENT.md, and write a new handoff.
```
