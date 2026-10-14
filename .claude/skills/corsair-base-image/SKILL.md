---
name: corsair-base-image
description: Use when adding, registering or updating a Corsair sandbox toolchain image or runtime/framework row. Follow current v2 image sources, immutable pins, native controls, matrix compatibility and qualification records.
---

# Corsair base image

Use `corsair-development` and `corsair-review`. Read SPEC-0082, `deploy/v2/runtime-matrix.yaml`, `tools/toolchain_images.py`, `tools/v2_canary.py` and `docs/qualification/openshell-toolchains.md`. Current source and records outrank historical v1 runbooks.

## Prepare one runtime

1. State the exact runtime/framework requirement and unsupported versions. Reuse the closest source under `deploy/qualification/toolchains/<name>/`; do not install a nearby runtime as a substitute.
2. Pin the official base image by digest and all fetched tools/dependencies by reviewed versions and hashes. Preserve offline caches, non-root user, fixture and resource/network constraints. Do not use unpinned package installs or `curl | sh`.
3. Add/update the Dockerfile, reviewed pin files and trusted fixture in that directory. Follow `tools/toolchain_images.py`'s actual preparation/identity conventions rather than restoring removed `tests/qualification` helpers. For Maven cache changes use `make maven-hashes TOOLCHAINS=<name>` and review the complete digest diff.
4. Run `make toolchain-images TOOLCHAINS=<name>` when Docker is available. Retain failed attempts and cleanup receipts. Installed versions and rendered Dockerfiles alone do not establish native behavior.

## Register and test

1. Update the operator-owned row in `deploy/v2/runtime-matrix.yaml` within the authorized developer scope. Match the built image, runtime/framework version, test placement, native run/diagnostic templates, exit-code map and declared build hosts. Investigated agents must not edit matrix, image pins or policy.
2. Add or update the matching framework skill and pass/fail canaries under `src/corsair/v2/skills/frameworks/<name>/`. Preserve the current marker/token interface and PoV polarity; no framework-specific branch belongs in the chain.
3. Run `make test-config`, affected matrix/outcome tests and `make canary` on prepared images. Prove supported selection, out-of-range refusal, known native pass/fail and existing-row regressions. Report missing Docker/images as unrun, not pass.
4. Run an admitted real case through both revisions before claiming native issue validation. Record exact source/image/policy identity, discovery/assertion outcomes and confirmed cleanup separately from agent inference accuracy.

Keep rows `image-only` until the current qualification gate actually passes. Follow the latest explicit decisions in `docs/development/CURRENT.md` and SPEC-0083 rather than a historical deferral. The v2 OpenShell backend is implemented, not live-qualified; use its current runbook and coordinator-owned cluster handover when the gate is authorized. Qualify each backend/driver separately, with explicit operator policy and no silent fallback. Historical commands on main are not automatically available v2 commands.

Update living records and hand off substantial work. Never weaken pins, network policy or evidence requirements to obtain a pass, and never delete failed receipts merely to force a clean rerun.
