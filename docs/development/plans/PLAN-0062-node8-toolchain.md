---
id: PLAN-0062
kind: plan
title: Node 8 toolchain image
status: in_progress
updated: 2026-10-13
related: [SPEC-0055, SPEC-0042, SPEC-0007]
---

# Node 8 toolchain image

## Objective and dependencies

Implement [SPEC-0055](../specs/SPEC-0055-node8-toolchain.md): the `node8` image, its trusted control and toolchain gate, qualified live on RIG0, then its matrix row. Stacked on the JDK 8 (#51) and CPython 3.7 (#55) branches through the same merge as the Perl 5.26 image (62d35f2), because the per-image preparation, `--language`, `TOOLCHAINS` selection and per-image gates come from them. The kind cluster is used one thread at a time; this thread follows the Perl 5.26 thread. A JavaScript runner and report parser is the next PR; without it no case runs.

## Steps

- [x] Read the five Node 8 cases' requirements from PR #61's report and pin upstream `node:8.17.0-buster-slim` by digest.
- [x] Fixture with Jest 24.8.0 and a lockfile written by npm 6.13.4 on Node 8.17.0; Dockerfile, `BASES`, `NODES`, trusted control, gate, guards and selection test.
- [x] Image-only build and gate commands in the cloud container.
- [ ] Live on RIG0 in `/home/al/git/corsair/.worktrees/claude/toolchain-node8-iqwqim`, evidence under that worktree's `.runs`: fresh cluster, `make toolchain-images TOOLCHAINS=node8`, `make toolchain-images-load TOOLCHAINS=node8`, `make qualify-toolchain TOOLCHAINS=node8`.
- [ ] Qualification report entry (artifact, prepared config/manifest digests, run table, failed attempts), matrix row `node-8.17.0-npm` with measured versions, CURRENT.md, handoff.
- [ ] Second PR: Jest runner and report parser against real Jest 24 output, then Mocha 2/5 and AVA 2.

## Validation and progress

2026-10-13, cloud container (not qualification). Node 8.17.0 from nodejs.org, SHASUMS256-checked, with its npm 6.13.4: `npm install --before=2019-12-31` resolved `jest-cli` 24.9.0 under `jest` 24.8.0, so the lockfile was regenerated with `--before=2019-06-30` (481 packages, all `registry.npmjs.org`, every entry with `integrity`); `jest --version` 24.8.0. Plain `npm ci` ran fsevents' install script (with the host's Node 22), hence `--ignore-scripts` everywhere.

Docker Hub returned 429 for `docker.io/library/node@sha256:c9025a77…`, so the same index digest was pulled from `mirror.gcr.io` (versions in the base: v8.17.0, 6.13.4, 1.21.1, Debian 10.2; `/lib64/ld-linux-x86-64.so.2` is a symlink into `/lib`). Image-only build with the container's proxy CA added in a local copy of the Dockerfile: both `npm ci` runs and the Jest run passed. Trusted control command as UID 10001 with `--network=none`: `jest_report` accepted 2 tests. The gate's `node_offline` against `docker exec` in that image: versions `v8.17.0 6.13.4 1.21.1 24.8.0`, Jest report, `ENOTCACHED`, `No tests found`, `SyntaxError`, assertion all as expected. `node_dependencies`' npm commands through the container's proxy (no OpenShell policy): `is-number@7.0.0` installed and required, absent package `E404`. A tampered `integrity` gave `EINTEGRITY`. None of this is sandbox or policy qualification.

`make test-config`: 1273 passed on the branch (main 8169be9 plus #51 and #55).

## Decisions and next action

`buster-slim`, Node 8.17.0 only, Jest 24.8.0 fixture, lockfile as the hash list (see SPEC-0055). Next: when the Perl 5.26 thread hands over the cluster, Al pastes the RIG0 message in this thread.
