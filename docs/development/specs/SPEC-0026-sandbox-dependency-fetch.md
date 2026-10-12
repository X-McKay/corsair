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

In scope: the standard registry for each benchmark ecosystem, reached only during a setup phase, with GET-only access, and a recorded resolved set with integrity digests. Excluded: private registries and registry credentials, registry mirrors or caches (a later option, not required now), publishing, network access while tests run, and any change to operator-owned pins or policies.

## Boundaries and design

**Registry allowlist.** Operator-owned and per ecosystem, attached as a policy revision only for the setup phase:

| Ecosystem | Resolver binaries | Hosts |
| --- | --- | --- |
| Python | `pip`, `python -m pip` | `pypi.org`, `files.pythonhosted.org` |
| Java | `mvn` | `repo.maven.apache.org`, `repo1.maven.org` |
| JavaScript | `npm` | `registry.npmjs.org` |
| Ruby | `gem`, `bundle` | `rubygems.org`, `index.rubygems.org` |
| Perl | `cpanm` | `cpan.metacpan.org`, `fastapi.metacpan.org` |

Each grant names the resolver's canonical binary path, HTTPS on port 443, REST `GET` only and `enforcement: enforce`. GET-only blocks publishing and data-carrying uploads to the registry; [SPEC-0006](SPEC-0006-openshell-policy.md) already qualified method-level denial with native structured responses. The [toolchain qualification](../../qualification/openshell-toolchains.md) already exercised a policy-admitted, hash-checked PyPI wheel download with HTTPS interception enabled; Java and the other ecosystems need the same admission. Other hosts, including repository-declared custom repositories in `pom.xml`, `.npmrc`, `pip.conf` or Gemfile sources, are denied and reported as `dependency` layer blockers, never added automatically.

**Phases.** One sandbox moves through three policy revisions, each loaded with `policy set --wait` and confirmed by a native denial event before the next step:

1. Source fetch: the repository host only (SPEC-0025).
2. Dependency setup: registry hosts only. The repository host and its credential placeholder are gone before this phase, so dependency install scripts cannot reach the repository with the token.
3. Build and test: no network. Tests, the environment agent's readiness check and later test execution run here. Java runs Maven offline (`-o`) after a setup-phase `dependency:go-offline`; a plugin or provider that still needs a download fails as `dependency`, not as a test result.

**Install-time code.** Package installs can run third-party code (`setup.py`, npm lifecycle scripts, Maven plugins). It runs only in phase 2, inside the sandbox, with GET-only access to the allowlisted registries and no credentials. Defaults: `npm ci --ignore-scripts` unless the repository's documented setup requires scripts, in which case the recipe records that it ran them; `pip` with `--only-binary :all:` when the project allows it. These are recipe defaults the environment agent can override only with a recorded reason.

**Resolved-set evidence.** The setup phase ends with a bounded, machine-readable record of what was installed, produced by the resolver's own native output: `pip install --report` (name, version, URL, sha256), the npm lockfile's `integrity` fields, Maven's resolved artifact list with repository checksums, and the equivalents for Ruby and Perl. It comes back through the existing bounded stdout receipt path (SPEC-0010), never as a file download. Where a lockfile with hashes exists, installation must use it (`pip --require-hashes`, `npm ci`, `bundle install --frozen`). The record is the dependency closure the environment agent reports and the setup-replay node reproduces.

**Replay.** The deterministic setup-replay node runs the same recipe in a fresh sandbox under the same phases and compares the new resolved set with the recorded one. A difference, such as a registry serving a new version for an unpinned range, is recorded as drift and blocks readiness unless the recipe pins the recorded versions. Public registries are mutable, so a later replay can fail where an earlier one passed; that is a recorded limitation of using public registries without a mirror.

**Failure attribution.** Registry TLS failure, policy denial, missing package, resolver conflict, install-script failure and budget exhaustion are distinct receipts, distinguishing policy denial from an unavailable registry as the toolchain qualification did. None of them counts as an application observation.

## Acceptance and validation

Offline checks: allowlist documents grant only the listed hosts, port 443, GET and the named binaries; phase revisions are ordered and the test phase grants nothing; recipe defaults are fixed; resolved-set parsers refuse missing digests, duplicates and unbounded output.

Live qualification, per ecosystem as it is admitted (Python and Java first, matching the initial support envelope), on two fresh admitted nodes with confirmed cleanup: a hash-locked install succeeds and its resolved set matches on replay; a POST to the registry is denied with a native policy response; a repository-declared custom repository is denied and reported; an install script reaching a non-allowlisted host is denied; after phase 3, a registry GET is denied with a native event; a test needing a missing plugin offline fails as `dependency`. Record bytes, request counts, time and resolved-set size.

This spec does not qualify builds, test discovery, the environment agent or any application observation.

## Decisions and open questions

The user chose standard public registries for now. Defaults chosen here: GET-only per-binary grants, three ordered policy phases, no network during tests, native resolver reports as the closure record, drift blocks readiness. Open: a pinned mirror or cache would remove registry mutability and is the expected next step if replay drift is observed; ecosystems beyond Python and Java are admitted one at a time as PLAN-0021 cases need them.
