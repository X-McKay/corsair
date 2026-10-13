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
- `src/corsair/nodes/runtime/environment.py`: the hand-off to the environment agent. The selected row becomes the only `EnvironmentInput.toolchains` entry (image from the operator's prepared-image receipt); no requirement, `unsupported`, `undetermined` or an unprepared row gives a `RuntimeStop`; `check_ready` refuses a ready result on another image or an unadmitted framework.
- Unit checks and matrix guards.

The hand-off is not yet called from the chain or durable workflow (G12). No new image is built or qualified. The `deploy/runtime-matrix.yaml` row schema is now a contract: the JDK 8 + JUnit 4 and CPython 3.7 toolchain threads add rows against it.

## Validation and blockers

- `make test-config`: 1024 passed after merging current main (8c29e16) and fixing Al's review findings (892 on the original base).
- Report: 39 of the 40 acquired cases fetched; 37 unsupported with the requirement named, 2 undetermined (no test framework), 0 supported on the existing images. Details, commands and the suggested rows are in PLAN-0046.
- The Jenkins parents are closed: RIG0 fetched them from repo.jenkins-ci.org, and the committed report uses the same POMs from the jenkinsci GitHub tags with identical rows. CVE-2023-31486 is `not_fetched` in the committed report (container egress) and undetermined on RIG0: its pin is Debian's whole perl repository, a case-definition question recorded in SPEC-0042.
- No live check was run, and none applies to this offline component.

## Decisions and next steps

Settled in SPEC-0042:
- one image per runtime version, not a kitchen-sink image (a selector-based hybrid is reserved);
- no new agent: the existing environment agent consumes the selection;
- strict Java selection by compiler level unless CI names other JDKs;
- one qualified framework per project suffices.

Next bounded actions:
1. Prepare and qualify a JDK 8 + Maven row with a JUnit 4 fixture, and a CPython row with an older pytest range, through one toolchain gate each on a fresh node, then add them to the matrix.
2. Decide CVE-2023-31486's project root (`cpan/HTTP-Tiny/` or perl core as its own runtime).
3. As part of G12, call `environment_input` from the chain and durable workflow, and `check_ready` on the agent's result.

Al reviews the draft PR and says "merge".

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then SPEC-0042, PLAN-0046 and this handoff. Inspect git/source state and verify recorded facts. Use the Corsair development skill. Add one new runtime matrix row (JDK 8 + Maven with a JUnit 4 fixture, or a CPython row with a pytest range below 9) by preparing its digest-pinned, hash-pinned image and passing the toolchain gate on a fresh RIG0 node under /home/al/git/corsair/.worktrees/<branch>; add the row only with that evidence. Call `corsair.nodes.runtime.environment.environment_input` from the chain (G12). Run make test-config, record actual results in PLAN-0046 or a new plan, update CURRENT.md and write a new handoff.
```
