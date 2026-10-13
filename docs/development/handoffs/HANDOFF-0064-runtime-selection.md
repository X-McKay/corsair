---
id: HANDOFF-0064
kind: handoff
title: Runtime selection from project build files
status: recorded
updated: 2026-10-13
related: [SPEC-0042, PLAN-0046, SPEC-0029, SPEC-0007]
---

# Runtime selection from project build files

## Verified state

Branch `claude/runtime-selection-8ts9z0`, based on main `334aa03`. Delivered offline under [SPEC-0042](../specs/SPEC-0042-runtime-selection.md) and [PLAN-0046](../plans/PLAN-0046-runtime-selection.md):

- `src/corsair/nodes/runtime/`: version sets, the combination rule, one detector per ecosystem (Python, Java, JavaScript, Ruby, Perl), typed requirement and selection contracts, the matrix loader and matcher.
- `deploy/runtime-matrix.yaml`: the two qualified images and the pytest 9.0.x runner row.
- `evals/benchmark/runtimes.py`: checkout, parents and report.
- `benchmarks/runtime-requirements.{md,json}`: the report over the benchmark cases.
- Unit checks and matrix guards.

Nothing is connected to the environment agent or the chain. No new image is built or qualified.

## Validation and blockers

- `make test-config`: 881 passed.
- Report: 39 of the 40 acquired cases fetched; 35 unsupported with the requirement named, 4 undetermined, 0 supported on the existing images. Details, commands and the suggested rows are in PLAN-0046.
- The container's egress refused salsa.debian.org and repo.jenkins-ci.org, so CVE-2023-31486 is `not_fetched` and two Jenkins parent POMs are missing. RIG0 can rerun `parents` and `report` to close both.
- No live check was run, and none applies to this offline component.

## Decisions and next steps

Settled in SPEC-0042:
- one image per runtime version, not a kitchen-sink image (a selector-based hybrid is reserved);
- no new agent: the existing environment agent consumes the selection;
- strict Java selection by compiler level unless CI names other JDKs;
- one qualified framework per project suffices.

Next bounded actions:
1. Prepare and qualify a JDK 8 + Maven row with a JUnit 4 fixture, and a CPython row with an older pytest range, through one toolchain gate each on a fresh node, then add them to the matrix.
2. Rerun the report on RIG0 with both parent repositories reachable.
3. As part of G12, pass the selected row to `EnvironmentInput.toolchains` and stop before the agent on `unsupported` or `undetermined`.

Al reviews the draft PR and says "merge".

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then SPEC-0042, PLAN-0046 and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. Add one new runtime matrix row (JDK 8 + Maven with a JUnit 4 fixture, or a CPython row with a pytest range below 9) by preparing its digest-pinned, hash-pinned image and passing the toolchain gate on a fresh RIG0 node under /home/al/git/corsair/.worktrees/<branch>; add the row only with that evidence. Rerun `evals/benchmark/runtimes.py parents` and `report` on RIG0 so the Jenkins parents and CVE-2023-31486 resolve. Run make test-config, record actual results in PLAN-0046 or a new plan, update CURRENT.md and write a new handoff.
```
