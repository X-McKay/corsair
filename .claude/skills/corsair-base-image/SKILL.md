---
name: corsair-base-image
description: Use when adding, registering or updating a Corsair sandbox toolchain image or runtime/framework row. Follow current v2 image sources, immutable pins, native controls, matrix compatibility and qualification records.
---

# Corsair base image

Use `corsair-development` and `corsair-review`. Read SPEC-0082, `deploy/v2/runtime-matrix.yaml`, `tools/toolchain_images.py`, `tools/v2_canary.py` and `docs/qualification/openshell-toolchains.md`. Current source and records outrank historical v1 runbooks.

## Rules that do not bend

- Build one image per exact runtime version; never use a nearby version as a substitute.
- Pin the official base by the **same digest string** in the Dockerfile and its matrix row; compare the strings, not merely resolved version labels.
- Keep fetched tools/dependencies reviewed and hash-pinned, with all probe/build contents available offline. Never use unpinned installs or `curl | sh`.
- Preserve non-root `USER 10001`, `HOME=/tmp`, and the trusted fixture under `/opt/corsair-fixture`, together with resource/network constraints.
- Never add a package to an image for one case. Images are reusable runtime toolchains, not case-specific environments.

## Prepare one runtime

1. State the exact runtime/framework requirement and unsupported versions. Reuse the appropriate source under `deploy/qualification/toolchains/<name>/`.
2. Add/update the Dockerfile, reviewed pin files and trusted fixture there. Follow `tools/toolchain_images.py`'s preparation/identity conventions, not removed `tests/qualification` helpers. For Maven cache changes use `make maven-hashes TOOLCHAINS=<name>` and review the complete digest diff.
3. Run `make toolchain-images TOOLCHAINS=<name>` when Docker is available. Retain failed attempts and cleanup receipts. Installed versions and rendered Dockerfiles alone do not establish native behavior.

## Register and test

1. Update the operator-owned row in `deploy/v2/runtime-matrix.yaml` within the authorized developer scope. Match the built image, runtime/framework version, test placement, native run/diagnostic templates, exit-code map and declared build hosts. Investigated agents must not edit matrix, image pins or policy.
2. Add or update the matching framework skill and pass/fail canaries under `src/corsair/skills/frameworks/<name>/`. Preserve the marker/token interface and PoV polarity; no framework-specific branch belongs in the chain.
3. Run `make test-config`, affected matrix/outcome tests and `make canary` on prepared images. Prove supported selection, out-of-range refusal, known native pass/fail and existing-row regressions. Report missing Docker/images as unrun, not pass.
4. Follow the lighter toolchain path chosen on 2026-10-13: a row lands as `evidence: image-only` only after a plain-Docker image build, the gate body and one real case at both commits. Record exact source/image/policy identity, discovery/assertion outcomes and confirmed cleanup separately from inference accuracy.
5. Only `evidence: live` after a passed milestone gate counts as qualified. Keep rows `image-only` until then; do not promote from Docker-only evidence. The current milestone-gate/cluster procedure is `docs/runbooks/openshell-v2.md`; follow its ownership/cleanup rules and the latest explicit decisions in `docs/development/CURRENT.md` and SPEC-0083. Qualify each backend/driver separately, with explicit operator policy and no silent fallback. Historical commands on main are not automatically v2 commands.

Update living records and hand off substantial work. Never weaken pins, network policy or evidence requirements to obtain a pass, and never delete failed receipts merely to force a clean rerun.
