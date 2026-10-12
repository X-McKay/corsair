---
id: SPEC-0026
kind: spec
title: In-sandbox dependency fetch from public registries
status: draft
updated: 2026-10-12
related: [IDEA-0004, SPEC-0025, SPEC-0006, SPEC-0007, SPEC-0010, ISSUE-0006, PLAN-0021]
---

# In-sandbox dependency fetch from public registries

## Goal and scope

After [SPEC-0025](SPEC-0025-sandbox-source-fetch.md) admits the source inside a sandbox, the environment agent must install the project's dependencies there. The user directed on 2026-10-12 that dependencies come from their standard public locations for now. This spec defines that phase: which registries a sandbox may reach, how, for how long, and what record of the resolved dependency set must survive. It is a policy and evidence contract that the environment agent's setup commands run inside, not an agent.

In scope: the standard registry for each benchmark ecosystem, reached only during a setup phase, with GET-only method and endpoint restrictions, and a complete realized dependency inventory with integrity digests. Excluded: private registries and registry credentials, registry mirrors or caches (a later option, not required now), publishing, network access while tests run, and any change to operator-owned pins or policies.

## Boundaries and design

**Registry allowlist.** Operator-owned and per ecosystem, attached as a policy revision only for the setup phase:

| Ecosystem | Resolver binaries | Hosts |
| --- | --- | --- |
| Python | `pip`, `python -m pip` | `pypi.org`, `files.pythonhosted.org` |
| Java | `mvn` | `repo.maven.apache.org`, `repo1.maven.org` |
| JavaScript | `npm` | `registry.npmjs.org` |
| Ruby | `gem`, `bundle` | `rubygems.org`, `index.rubygems.org` |
| Perl | `cpanm` | `cpan.metacpan.org`, `fastapi.metacpan.org` |

Each grant names the resolver's canonical binary path, HTTPS on port 443, REST `GET` only and `enforcement: enforce`. [SPEC-0006](SPEC-0006-openshell-policy.md) already qualified method-level denial with native structured responses.

**What GET-only does and does not guarantee.** The guarantee is a method and endpoint restriction: only the listed hosts, only `GET`, so publishing and request-body uploads are refused. It does not prevent outbound disclosure. Code running during setup can encode data in the path, query or headers of an allowed `GET` to an allowed registry, and the request leaves even if the response is a 404 ([RFC 9110, section 17.9](https://www.rfc-editor.org/rfc/rfc9110.html#section-17.9)). A binary grant does not make that binary trustworthy either: an allowed interpreter or resolver runs whatever install-time code it is given. For public source this residual disclosure is accepted and recorded, since the source is already public. For private source it is not acceptable: phase 2 with install-time code and registry egress is **not admitted for private repositories** until a separate constrained acquisition design is specified and qualified. The expected shape is resolution in a sandbox that holds only the dependency manifests, never the private source, populating an operator-owned offline mirror that the build sandbox then reads with no external egress. Until then, a private repository can reach readiness only if its dependency state needs no network. The [toolchain qualification](../../qualification/openshell-toolchains.md) already exercised a policy-admitted, hash-checked PyPI wheel download with HTTPS interception enabled; Java and the other ecosystems need the same admission. Other hosts, including repository-declared custom repositories in `pom.xml`, `.npmrc`, `pip.conf` or Gemfile sources, are denied and reported as `dependency` layer blockers, never added automatically.

**Phases.** One sandbox moves through three policy revisions, each loaded with `policy set --wait` and confirmed by a native denial event before the next step:

1. Source fetch: the repository host only (SPEC-0025).
2. Dependency setup: registry hosts only. The repository host and its credential placeholder are gone before this phase, so dependency install scripts cannot reach the repository with the token.
3. Build and test: no network. Tests, the environment agent's readiness check and later test execution run here. Java runs Maven offline (`-o`) after a setup-phase `dependency:go-offline`; a plugin or provider that still needs a download fails as `dependency`, not as a test result.

**Install-time code.** Package installs can run third-party code (`setup.py`, npm lifecycle scripts, Maven plugins). It runs only in phase 2, inside the sandbox, with GET-only access to the allowlisted registries and no credentials, and only for public source (see above). Defaults: `npm ci --ignore-scripts` unless the repository's documented setup requires scripts, in which case the recipe records that it ran them; `pip` with `--only-binary :all:` (required in the first release, per the inventory below). These are recipe defaults the environment agent can override only with a recorded reason.

**Realized dependency inventory.** Resolver reports are not the complete closure. `pip install --report` lists only distributions installed by that invocation, omits already-satisfied packages, and does not cover isolated build requirements, so an sdist can report the same URL and hash on two runs while a different build backend produces a different wheel ([installation reports](https://pip.pypa.io/en/stable/reference/installation-report/), [build isolation](https://pip.pypa.io/en/stable/reference/build-system/)). A Maven dependency list omits plugins and their dependencies, and lockfile `integrity` fields describe intended inputs rather than realized bytes. The closure record is therefore an inventory of what is actually on disk after setup, produced by an operator-owned script that runs after phase 2 with no network:

| Ecosystem | Covered inputs | Inventory |
| --- | --- | --- |
| All | Image-provided toolchain and system packages | Toolchain image digest, plus native interpreter/JDK/resolver versions |
| Python | Every distribution in the target environment, including pre-installed ones | `pip inspect` for the environment, plus SHA256 of every file each distribution's `RECORD` lists, verified against the bytes on disk. Installs use `pip install --no-compile` and tests run with `PYTHONDONTWRITEBYTECODE=1` (as the SPEC-0018 fixture already does), so no bytecode is generated |
| Python build dependencies | Isolated build environments | Wheels only (`--only-binary :all:`) in the first release, so no build backend runs; a project needing an sdist build is `unsupported` until build-requirement inventory is specified |
| Java | Project dependencies, plugins, plugin dependencies, extensions | Path and SHA256 of every artifact file (`.jar`, `.pom` and other resolved artifacts) in the Maven local repository after `dependency:go-offline` and an offline build, each also checked against the repository checksum Maven recorded |
| JavaScript | Installed packages | Path and SHA256 of every file under `node_modules` after `npm ci` |
| Ruby, Perl | Not yet defined | Admission blocked until a coverage row is specified |

**Generated files.** Identical installs can still write differing bytes that are not dependency inputs: Python bytecode caches, which embed timestamps or depend on compilation order ([invalidation modes](https://docs.python.org/3.12/library/py_compile.html#py_compile.PycInvalidationMode)), and resolver bookkeeping such as Maven's `_remote.repositories`, `*.lastUpdated`, `resolver-status.properties` and `maven-metadata-*.xml`, or npm's `node_modules/.package-lock.json`. Differences there are not drift, but arbitrary differences must not be ignored either. The treatment is: prevent generation where a native option exists (Python `--no-compile` and `PYTHONDONTWRITEBYTECODE=1`); otherwise each ecosystem has an explicit, operator-owned list of generated bookkeeping paths that are recorded by presence and compared by presence only. Every other file, including all executable dependency content, is compared by SHA256. A file that is neither listed nor hashed blocks readiness. Pip's own install metadata (`INSTALLER`, `REQUESTED`, `direct_url.json`) is deterministic for identical inputs and is hashed like any other file.

The inventory comes back through the bounded stdout receipt path (SPEC-0010) as path/digest lines or, if larger than the output bound, is refused rather than truncated. Where a lockfile with hashes exists, installation must use it (`pip --require-hashes`, `npm ci`, `bundle install --frozen`). If coverage for an ecosystem is incomplete, the environment cannot be admitted ready. The inventory is the dependency closure the environment agent reports and the setup-replay node compares.

**Replay.** The deterministic setup-replay node runs the same recipe in a fresh sandbox under the same phases and compares the new realized inventory with the recorded one, file by file. A difference, such as a registry serving a new version for an unpinned range, is recorded as drift and blocks readiness unless the recipe pins the recorded versions. Public registries are mutable, so a later replay can fail where an earlier one passed; that is a recorded limitation of using public registries without a mirror.

**Failure attribution.** Registry TLS failure, policy denial, missing package, resolver conflict, install-script failure and budget exhaustion are distinct receipts, distinguishing policy denial from an unavailable registry as the toolchain qualification did. None of them counts as an application observation.

## Acceptance and validation

Offline checks: allowlist documents grant only the listed hosts, port 443, GET and the named binaries; phase revisions are ordered and the test phase grants nothing; private-source recipes have no phase 2 egress; recipe defaults are fixed; inventory parsers refuse missing digests, duplicates, unknown ecosystems and oversize output.

Live qualification, per ecosystem as it is admitted (Python and Java first, matching the initial support envelope), on two fresh admitted nodes with confirmed cleanup: a hash-locked install succeeds and its realized inventory matches on replay; two fresh installs of the same artifacts produce identical inventories (the positive case that catches spurious generated-file drift); a replay where only a build or plugin dependency changes while the top-level reported set stays constant is detected as drift; a pre-installed package that differs between images is detected; a POST to the registry is denied with a native policy response; a repository-declared custom repository is denied and reported; an install script reaching a non-allowlisted host is denied; an allowed-host `GET` carrying a synthetic marker in its path and query is observed reaching the registry in public mode, documenting the residual disclosure, and has no route at all in private mode; after phase 3, a registry GET is denied with a native event; a test needing a missing plugin offline fails as `dependency`. Record bytes, request counts, time and resolved-set size.

This spec does not qualify builds, test discovery, the environment agent or any application observation.

## Decisions and open questions

The user chose standard public registries for now. Defaults chosen here: GET-only per-binary grants, three ordered policy phases, no network during tests, realized on-disk inventory as the closure record with generated files prevented or listed explicitly, wheels-only Python in the first release, drift blocks readiness, and no registry egress for private source until a constrained acquisition design is qualified. Open: a pinned mirror or cache would remove registry mutability and is the expected next step if replay drift is observed; ecosystems beyond Python and Java are admitted one at a time as PLAN-0021 cases need them.
