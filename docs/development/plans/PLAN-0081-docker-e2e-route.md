---
id: PLAN-0081
kind: plan
title: Plain Docker end-to-end route, unqualified (risk accepted)
status: in_progress
updated: 2026-10-13
related: [SPEC-0031, SPEC-0032, SPEC-0033, SPEC-0062, PLAN-0034, PLAN-0079]
---

# Plain Docker end-to-end route, unqualified (risk accepted)

## Objective and dependencies

Al (2026-10-13 17:42Z): run end to end outside kind and OpenShell, risk accepted, to iterate without bringing a
cluster up and down or troubleshooting its network; make it work first, infra kinks later. The chain, stage order,
runner core and witness stay as they are; only the sandbox behind the existing ports changes. The fixture CLI's
host route admits only the reviewed SPEC-0018 bytes, so a live author's tests stopped there; the OpenShell route
(PLAN-0034) needs a qualified cluster.

Built on PLAN-0079's branch (#109), which already moved the image-only Docker harness into product code
(`corsair.adapters.docker_image.DockerCase`) and gives `corsair investigate` a Docker Preparation for the
environment stage and Docker revision runners. This plan reuses them; it adds no second Docker layer.

## Steps

- [x] `evals/fixture_e2e/docker.py`: each runner call is a fresh `DockerCase` of the local `cpython-3.12-pytest`
  image (`make toolchain-images TOOLCHAINS=python`): `--network=none`, `--cap-drop=ALL`, no-new-privileges, the
  variant's source copied in fresh, the patch written next to it, the OpenShell route's pytest argv and witness probe.
  Environment identity declares the local config id, argv, the image's hash-pinned wheels and policy
  `docker-offline-cap-drop-all`; each revision's source is the digest the Docker workspace records.
- [x] `python -m evals.fixture_e2e.run --sandbox docker --images <json>` (or `CORSAIR_IMAGES`), with `--live` as
  before; `configuration.json` and `result.json` record `runner.route = docker`,
  `runner.qualification = unqualified` and the basis; the printed summary repeats both.
- [x] Offline tests with a fake docker CLI (`tests/agents/test_fixture_docker.py`): an authored (non-reviewed) patch
  runs in an offline container and the container is removed; every stage runs and records itself unqualified; the
  route refuses to start without the row's local image.
- [ ] Never the host network for the setup container and the environment stage's sandbox: the Node thread lands it
  on #109 (`registry_access`); this branch takes that commit.
- [ ] First live proof on RIG0 (fixture case, all stages live, Docker), when the model is free.
- [ ] Python on the `corsair investigate` Docker route: a pytest harness entry with setup and witness recorders
  (PLAN-0079's last step) so the corpus cases run there too.

## Validation and progress

- 2026-10-13, cloud container, dockerd 29.8.2 with `--registry-mirror=https://mirror.gcr.io` (Docker Hub answered
  429): `make toolchain-images TOOLCHAINS=python` built `corsair-python` config
  `sha256:6be4d96f7e804e7e5ef9a7a0870bd769806e43dc3a67e81c2ad5a105c470997f`, trusted control passed.
- Scripted Docker check: `PYTHONPATH=src:. .venv/bin/python -m evals.fixture_e2e.run --sandbox docker --images
  <json> --evidence .runs/fixture-e2e-docker/scripted-001` reached `complete`: baseline control passed and security
  test failed, candidate both passed, both witnesses admitted, gate `completed / reproduced / verified`, scripted
  assessment admitted (`completed / inconclusive / not_verified`), workspace cleanup confirmed, no container left.
  Evidence stays in the cloud container (not committed).
- `tests/agents/test_fixture_docker.py` 3 passed; with the fixture sandbox, composition and case e2e tests 39 passed.

## Decisions and next action

- Plain Docker is not the sandbox the project qualifies: no OpenShell policy, gateway, admission or egress
  enforcement stands behind it, and the container runs as the operator's uid. Its results are development evidence
  only and say so in every record; the OpenShell route remains the one that qualifies a result.
- Next: the live fixture run on RIG0 on the coordinator's word (worktree under `.worktrees/`, evidence in that
  worktree's `.runs`, `CORSAIR_STAGE_PROFILES=evals/fixture_e2e/stage-profiles.json`, no blind retries).
