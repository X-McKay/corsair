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
- Batch of six live runs, as reported by the RIG0 run session (same worktree, commit, provider and stage profiles as
  live-001; evidence `.runs/fixture-e2e-docker/live-001..006`, redacted tarball
  `/mnt/project-files/e2e-docker-batch.tar.gz`). Seconds are identification / planning / authoring / assessment.
  Three of six reached reproduced / verified. Identification and planning were stable in all six, no run hit a tool
  limit, and both witnesses were admitted in every run that executed tests.
  - live-001: reproduced / verified, admitted; the test asserted ValueError (4.5 / 29 / 22 / 28).
  - live-002: inconclusive; the assessment proposed not_reproduced and was not admitted. The security test wrote
    `allowed/note.txt` without creating `allowed/` and raised FileNotFoundError on both revisions before the
    traversal call; authoring accepted it (6 / 27 / 12 / 48).
  - live-003: reproduced / verified, admitted; the test asserted any exception (7 / 28 / 29 / 43).
  - live-004: reproduced / verified, admitted; the test asserted ValueError (4 / 23 / 24 / 36).
  - live-005: reproduced / not_verified, admitted at that level; the test asserted the result is not "outside" and
    did not expect the fix's ValueError, so the fixed revision failed it (9 / 30 / 57 / 64).
  - live-006: stopped at authoring; the final answer had prose before the JSON, its one correction was rejected, and
    its test only checked that an outside file was unchanged (authoring 70 s).
- Cloud container (dockerd with `--registry-mirror=https://mirror.gcr.io`): scripted Docker runs at da0667f and on the
  merged head reached `complete`, gate reproduced / verified, all three containers removal-confirmed.
- `make test-config` 1782 passed at da0667f's parent content; after merging c0a1904, the fixture Docker, sandbox,
  composition and case e2e tests passed (41). CI `offline-guards` green on da0667f.

## Decisions and next steps

- The batch's failures are authoring quality (a test that fails before the traversal call, a test that rejects the
  fix's safe behaviour, prose around the final JSON), not the route: each executed run ran in Docker as planned.

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
