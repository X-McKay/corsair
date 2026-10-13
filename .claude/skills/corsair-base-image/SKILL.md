---
name: corsair-base-image
description: Use when adding, registering or bumping a Corsair sandbox toolchain base image (a new runtime version such as JDK 8 or CPython 3.7, or a new language). Follow the standard image source, pins, fixture, preparation, toolchain gate, runtime-matrix row and records.
---

# Corsair base image

Resolve paths from the repository root. Use this with `corsair-development` (records, validation) and `corsair-review` (final review); it adds the image-specific steps only and grants no extra authority. Read [SPEC-0007](../../../docs/development/specs/SPEC-0007-openshell-toolchains.md), the [toolchain qualification report](../../../docs/qualification/openshell-toolchains.md) and SPEC-0042 (runtime selection) before starting.

## Rules that do not bend

- **One image per runtime version** (SPEC-0042). Never add a second runtime to an existing image, and never register a nearby version as a substitute: a project that needs JDK 8 is unsupported until a JDK 8 row is qualified.
- **Official upstream base, pinned by digest.** `FROM <registry>/<official image>@sha256:<64 hex>`, the same string in the Dockerfile, in `BASES` and in the matrix row. Record the tag, platform, manifest digest and the upstream Dockerfile source commit in the qualification report.
- **Offline, hash-pinned contents.** Everything the image adds is fetched during trusted preparation and verified: Python wheels by exact URL + SHA-256 (`--no-index --require-hashes`), Maven artifacts through Maven's strict checksums (`-C`) with the resulting cache inventoried to `/opt/corsair-m2.sha256`, single downloaded tools by a checked-in `*.sha256` file (`sha256sum -c` in the build). No unpinned `apt`, `pip`, `npm` or `curl | sh`.
- **Image layout.** Fixture project at `/opt/corsair-fixture`, offline caches under `/opt/corsair-*`, `ENV HOME=/tmp`, final `USER 10001:10001`. Anything the sandbox must read is added to the gate's `toolchain_policy` read-only list.
- **Qualification is live.** A Dockerfile, build, trusted control or version string is not qualification. A matrix row cites a toolchain gate that passed on RIG0 on a fresh kind node. Until then the row's `qualification.note` starts `PENDING live gate.` and the PR, plan and `CURRENT.md` say unqualified.
- **Operator-owned.** Pins, the matrix, policies and budgets are never agent-editable and never weakened to get a pass. No blind retries; retain failed attempts in the report.

## Steps

Name the image directory after the runtime version (`python37`, `java8`, `node8`); the existing `python` and `java` directories are the CPython 3.12 and JDK 17 images. Reference walks: `deploy/qualification/toolchains/java8` (PR #51, SPEC-0045/PLAN-0049) and the CPython 3.7 image thread.

1. **Records.** Spec + plan from `docs/development/templates/` (next unused numbers; check open PR branches for collisions with `git ls-tree`). The spec names: the cases the row unblocks (from SPEC-0042's report, `benchmarks/runtime-requirements.md`), the exact upstream tag/digest, runtime, build tool and framework versions, and what stays unsupported (for example JUnit 4 before 4.12).
2. **Image source** `deploy/qualification/toolchains/<dir>/`:
   - `Dockerfile` starting with the pinned `FROM`, following the closest existing image of the same language line for line, so the diff shows only the version difference.
   - Pin files: `requirements.txt` + `wheels.json` (Python: name, version, filename, url, sha256, one wheel per dependency, Python-tag compatible with the runtime), `pom.xml` with exact plugin versions (Java), `*.sha256` for any single tool such as the JUnit console launcher.
   - A fixture project with the same test shape as its siblings (Java: `corsair.NativeTest` with `nativeRoundtrip` and `nativeRuntime` asserting the image's feature version; Python: `test_native.py`). The fixture uses the framework version the row will claim.
3. **Preparation** `tests/qualification/prepare_toolchains.py`: add `'<dir>': '<base digest>'` to `BASES`; extend `control()` so the trusted control runs the fixture offline (`--network=none`, UID 10001) and asserts test count, names and zero failures/skips; keep per-image `source_hashes(language)` and the `--language` option (both from PR #51) so adding an image does not invalidate the others' receipts. Wheel download and network mode follow the language branch in `main()`.
4. **Toolchain gate** `tests/qualification/test_toolchains.py`: add the directory to the sandbox loop, its read-only paths to `toolchain_policy`, and its per-image expectations (javac/runtime version strings, framework's assertion message and engine, as in the `JAVA` table). The gate must cover the same offline diagnostics as the sibling image (missing dependency, no discovery, compilation/collection, assertion) and, where a Corsair runner exists for the language, the runner's own discovery and execution argv on the fixture.
5. **Framework support** if the row brings a new test framework or generation: admit it in `src/corsair/agents/environment/frameworks.py`, name it in the `prepare-environment` skill, and add a `frameworks` matrix row whose `versions` range is only what was actually run. A framework with no Corsair runner and report parser is not a row; record it as a gap.
6. **Matrix row** in `deploy/runtime-matrix.yaml` (from SPEC-0042, PR #48; if the matrix or the PR #51 preparation changes are not on your base yet, stack on that branch or wait for its merge rather than copying its files): `id` (`<runtime>-<version>-<tool>`), `language`, `base_image` (same digest), `image_source`, `runtime` `{name, version}` with the version measured in the image, `tools` with exact versions, `selector: {}`, and `qualification` `{records, report, note}`. Rows are tried in order; put a row where the first-match rule cannot select it for a requirement another row should own. `tests/configuration/test_runtime_matrix.py` (PR #51) checks rows against `BASES`, Dockerfiles and cited records.
7. **Offline checks** (cloud or RIG0): `make test-config`; a selection check that a representative build file selects the new row, that an out-of-range version is unsupported with the need named, and that existing rows are still selected for their cases. Where Docker is unavailable, say so; resolving the pins on another runtime is not evidence for this image.
8. **Live on RIG0** (only one thread uses the kind cluster at a time; hand over by cross-session message; worktree under `/home/al/git/corsair/.worktrees/<branch>`, evidence under `.runs`):
   - `uv run --locked python -m tests.qualification.prepare_toolchains build --language <dir>` then `... load --language <dir>` (or `make toolchain-images` / `make toolchain-images-load` for every image). A retained `.cache/toolchains/<dir>` from an earlier attempt is inspected and archived, never deleted to force a rebuild.
   - `make qualify-toolchain` on a fresh admitted node; then one real benchmark case that the row unblocks, on its unchanged build files, through the language's runner. An image-only run outside OpenShell is recorded as image-only.
9. **Record the result**: fill the qualification report (artifact table row with tag/digest/source commit, prepared config/manifest digests, run table with JUnit seconds, SDK/command counts, sandbox ids and confirmed cleanup, every failed attempt and its correction), replace `PENDING live gate.` with the measured versions, update the plan, `CURRENT.md` (one row per PR; keep all rows on conflict), and SPEC-0042's report if the supported-case count changed. Add a handoff with `corsair-handoff`.

## Review checklist

Same digest in Dockerfile, `BASES` and row; no unpinned fetch; fixture claims only the versions the row claims; gate covers the sibling's diagnostics; row's `runtime.version` is measured, not the tag; unqualified stays visibly unqualified; no fallback or version override added anywhere; failed attempts retained.

Do not use this skill to change a project's own versions, to add a package to an image for one case, or to qualify sandbox properties unrelated to the toolchain.
