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
- Tests: `tests/unit/test_git_acquire.py` (11), `tests/configuration/test_benchmark_sources.py` (2).

It does not depend on or edit the files of draft PR #39 (case loader, IDEA-0005); it reads the inventory directly and can switch to that loader after both merge.

## Validation and blockers

- `make test-config`: 866 passed (853 on main plus 13 new).
- Network run from this cloud container (evidence `.runs/acquire-20261013/`, `.runs/acquire-20261013-fsck-warn/`, ignored): 40 of 50 cases resolve to a commit; 39 acquired and verified; 1 refused at `host_network` (salsa.debian.org blocked by this container's egress proxy, CVE-2023-31486). Six repositories were refused by default strict transfer fsck on historical format-only objects and acquired on an explicit rerun with those ids downgraded.
- `GitSource` capture of the fix commit: 28 completed, 11 refused (3 over 4,096 files, 2 symlink/submodule, 6 its own strict fsck on the same format-only objects). Details per case in the pins file and PLAN-0041.
- Not run: the SPEC-0025 sandbox fetch (blocked on the storage quota, SPEC-0036 on PR #39), any build, test or case admission. Merge-commit fixes (6 cases) have no single-parent baseline candidate. Whether a first parent is the vulnerable revision is unverified for every case.

## Decisions and next steps

Settled here: complete ancestry by default so the qualified `GitSource` can capture; fetch from the repository named in the fix reference and flag inventory disagreement; format-only fsck downgrade is opt-in, three ids, recorded; repositories and captured objects are deleted after a run unless `--keep`. Next: decide whether `GitSource` should accept the same format-only downgrade or capture without walking ancestry (SPEC-0012), repository-scale source access for the cases over capture ceilings (IDEA-0005 G2b), then the sandbox fetch once storage is qualified. Acquire CVE-2023-31486 from a host whose egress allows salsa.debian.org, or find the equivalent upstream HTTP-Tiny commit during case admission.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then SPEC-0037, PLAN-0041 and this handoff. Inspect git/source state and verify recorded facts against benchmarks/source-pins.json. Use the Corsair development skill. Next bounded action: decide and implement how GitSource (SPEC-0012) captures the six repositories it refuses on format-only fsck messages, or start repository-scale source access for the cases over the capture ceilings. Do not weaken fsck beyond the three named message ids or treat a first parent as the vulnerable revision without case admission. Run make test-config, preserve evidence under .runs/, update the records and CURRENT.md, and write a new handoff.
```
