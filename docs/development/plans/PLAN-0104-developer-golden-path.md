---
id: PLAN-0104
kind: plan
title: Shared developer skills and configuration golden path
status: complete
updated: 2026-10-14
related: [SPEC-0082, SPEC-0083]
---

# Shared developer skills and configuration golden path

## Scope and boundaries

PR #176 restores `make test-config`, removes duplicated retired v1 architecture from five canonical skills, fixes current-work paths and dynamic scorer discovery, and preserves Codex symlinks and qualification authority. Structural checks do not certify model/client compliance. The closed audit/roadmap PR #178 is not a dependency and is not pursued.

## Review follow-up

Rebased onto inspected develop `a00bbbc96d3b97838398693dea3dcae7c43da6bb`. Address the owner's 2026-10-14 review:

1. Restore a concise "Rules that do not bend" list in `corsair-base-image`: one exact runtime version per image, no nearby-version substitute, the same official base digest string in Dockerfile and matrix row, reviewed offline hash-pinned contents, non-root `USER 10001`, `HOME=/tmp`, fixture `/opt/corsair-fixture`, and no package added for one case.
2. State the lighter toolchain entry criterion chosen on 2026-10-13: a row lands as `evidence: image-only` only after a plain-Docker build, gate body and one real case at both commits. Only `evidence: live` after a passed milestone gate counts as qualified.
3. Link the active procedure at `docs/runbooks/openshell-v2.md`, retaining current coordinator/ownership/cleanup rules. Do not resurrect unavailable `qualify-image`/`archive-runs` commands from v1.
4. Add cheap regression guards for the restored instructions and active runbook. Preserve one canonical skill source and existing `.agents/skills` symlinks.
5. Re-run skill/configuration and full offline checks, cleanup/re-test and update the existing PR. Do not run a live image/cluster gate or merge automatically.

## Validation

Earlier bdbb2a91 standalone checks: configuration/focused 107 passed, full serial/four-worker 1637 passed/113 skipped. These are historical; a00bbbc review follow-up evidence is recorded below after execution.

Review follow-up validation completed on the pinned a00bbbc base; commands/results below.

Unrun: actual Claude/Codex client compliance, Docker image builds, real case-at-both-commits and milestone OpenShell gate. Restoring the instructions and checking their presence is not evidence those live steps passed. No rows, image pins, provider policies, agent prompts or baselines are changed/promoted. Keep `.runs/`, `.state/`, credentials and private diagnostics out of Git.

## Completed owner-review validation

Base: `a00bbbc96d3b97838398693dea3dcae7c43da6bb`.

| Check | Result |
| --- | --- |
| Focused boundary/configuration tests | 108 passed |
| Four-worker make test-v2 | 1703 passed, 113 skipped |
| Serial make test-v2 | 1703 passed, 113 skipped |
| Diff cleanup and focused re-test | diff check passed; 108 passed |

All five skill metadata checks and make test-config passed. Structural guards do not prove real client compliance or a live image gate.

All owner review items are addressed in this branch. The current PR/plan/index provide the next-session context: inspect source/CI, review the bounded diff and keep live qualification separate. PR #178 remains closed and no audit/roadmap continuation is part of this follow-up. Do not merge or promote automatically.
