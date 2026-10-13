---
id: HANDOFF-0104
kind: handoff
title: Plain Docker end-to-end route and its first fully live pass
status: recorded
updated: 2026-10-13
related: [PLAN-0081, PLAN-0079, SPEC-0031, SPEC-0033]
---

# Plain Docker end-to-end route and its first fully live pass

## Verified state

Branch `claude/docker-e2e-route-99auac` (PR #113), stacked on PR #109's branch (`claude/toolchain-node8-iqwqim`,
merged in at c0a1904). Delivered: `evals.fixture_e2e.run --sandbox docker` (fresh offline container per runner call
from the local `cpython-3.12-pytest` image through `corsair.adapters.docker_image.DockerCase`), `corsair run
--sandbox docker` (its only route), every record labelled `route docker`, `qualification unqualified`; container
removal written to `docker/containers.json`; explicit failures instead of `assert` in `DockerCase` and `commit_tree`
(review note). Plain Docker is development evidence only: no OpenShell policy, gateway, admission or egress
enforcement, the container runs as the operator's uid.

## Validation and blockers

- First fully live pass, RIG0, frozen da0667f, worktree `/home/al/git/corsair/.worktrees/docker-route-live`, image
  `docker.io/library/corsair-python:61a3e8db1afb1726` config
  `sha256:68f08d0e933760a96e97ccafb3604a11ebddd0779e04c355f3a552dcf332832b`, provider
  `.runs/fixture-e2e-20261012/provider.json`, `evals/fixture_e2e/stage-profiles.json`, model not shared (as relayed by
  the RIG0 session): scripted control and the live run (identification, planning, authoring, assessment live) both
  `complete`, gate `completed / reproduced / verified`. Live: admission admitted, disposition reproduced / verified,
  no rejections; baseline control passed and security test `test_read_document_path_traversal` failed ("Expected
  ValueError"), candidate both passed; witnesses admitted (baseline effect observed; candidate absent, safe behaviour
  ValueError). Usage: identification 2 requests / 1 tool call / 4.5 s, planning 3 / 2 / 28.7 s, authoring 6 / 4 /
  22.1 s, assessment 10 / 9 / 28.1 s. Evidence on RIG0:
  `/home/al/git/corsair/.worktrees/docker-route-live/.runs/fixture-e2e-docker/{scripted-001,live-001}`.
- Cloud container (dockerd with `--registry-mirror=https://mirror.gcr.io`): scripted Docker runs at da0667f and on the
  merged head reached `complete`, gate reproduced / verified, all three containers removal-confirmed.
- `make test-config` 1782 passed at da0667f's parent content; after merging c0a1904, the fixture Docker, sandbox,
  composition and case e2e tests passed (41). CI `offline-guards` green on da0667f.

## Decisions and next steps

- The route is a stand-in behind the same ports; the OpenShell route stays the only one that qualifies a result.
- Next: retarget #113 to main once #109 merges; Docker runs of corpus cases through `corsair run` (PLAN-0079's
  pytest entry) as the coordinator schedules them.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, then PLAN-0081, PLAN-0079 and this handoff. Inspect git/source state
and verify recorded facts. Use the Corsair development skill. Run the next corpus case through `corsair run
--sandbox docker` on RIG0 when the coordinator says the model is free (worktree under .worktrees, evidence in that
worktree's .runs, absolute --evidence, no blind retries). Keep every Docker result labelled unqualified. Run
`make test-config`, update PLAN-0081/CURRENT.md, and write a new handoff.
```
