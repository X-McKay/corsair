---
id: SPEC-0055
kind: spec
title: Node 8 toolchain image
status: draft
updated: 2026-10-13
related: [SPEC-0042, SPEC-0007, SPEC-0026, SPEC-0045, SPEC-0046, PLAN-0062]
---

# Node 8 toolchain image

## Goal and scope

Al's goal (2026-10-13) is that every benchmark case runs end to end on its own declared runtime. SPEC-0042's report (PR #61) finds five JavaScript cases whose build files or CI admit Node 8 and no other qualified runtime: CVE-2020-8116 (npm, AVA `^2.1.0`), CVE-2020-15123 (npm 5-6 lockfile, Jest `^24.8.0`), CVE-2020-7730 (Travis Node 8 only, npm 5-6 lockfile, Jest `^24.8.0`), `@vivaxy/here-3.1.0` (Yarn 1, Mocha `^2.1.0`) and GHSA-xxvw-45rp-3mj2 (npm, Mocha `^5.2.0`). This spec adds the image those cases need: Node.js 8.17.0 with npm 6.13.4 and Yarn 1.21.1, an offline Jest 24.8.0 fixture, and its toolchain gate. CVE-2017-18077 (Node 7 or earlier, tape) and the two undetermined cases stay out of scope.

The image alone unblocks no case: Corsair has no JavaScript test runner or report parser yet, so a case still stops at the framework. The runner (Jest first, two cases; then Mocha, two cases; AVA one case) is a second PR under its own spec. Not in scope: Yarn offline installs (only the Yarn version is checked), native addons (the slim base has no compiler or Python, so a case that builds one fails at its dependency step, attributably), and the `nodejs`/`javascript` matrix and framework rows, which wait for the live gate.

## Boundaries and design

`deploy/qualification/toolchains/node8` is `FROM` the official `node:8.17.0-buster-slim` index digest `sha256:c9025a77a42d87e95433337ac581c0d42810c1263f0e78802691046920d1560b` (Linux amd64 manifest `sha256:93064a406609dcbb0f815efd9ab96daeae4343e74389aa0e632d372700485f19`), built from nodejs/docker-node commit `3c10e908934690b6af4f8f83b7e5e1da49926b34` directory `8/buster-slim` (docker-library/official-images `library/node`, 2019-12-18 entry, the last Node 8 release). The upstream image itself checks the Node tarball against the release SHASUMS and Yarn against its GPG signature; the Dockerfile asserts the three versions before anything else.

Contents are pinned by the fixture's checked-in `package-lock.json` (lockfile v1, as npm 6 writes it; 481 packages each with a SHA-512 `integrity`, resolved on 2026-10-13 with npm 6.13.4 under Node 8.17.0 and `--before=2019-06-30` so the closure is contemporary with Jest 24.8.0 and no package newer than Node 8 support is drawn in). Trusted preparation runs `npm ci --ignore-scripts` against that lockfile into `/opt/corsair-npm`: `npm ci` refuses a lockfile that disagrees with `package.json` and any tarball whose SHA-512 differs, so the lockfile is the reviewed hash list the skill asks for and no separate inventory is kept. A second, `--offline` `npm ci` from that cache and the fixture's Jest run prove the cache is complete. Install scripts never run. The fixture (`/opt/corsair-fixture`: `package.json`, `package-lock.json`, `native.test.js` with `nativeRoundtrip` and `nativeRuntime`, the latter asserting Node major 8) is the same shape as its siblings, with identifier titles so the Jest runner's ids can address them; `HOME=/tmp`, user 10001.

`prepare_toolchains.py` adds `node8` to `BASES`, a `NODES` table and the trusted control (offline `npm ci` from the cache, then Jest's own `--json` report checked by `jest_report`: both tests ran and passed, nothing else ran). The gate `test_native_node8_toolchain` (`TOOLCHAINS=node8`) runs in an OpenShell sandbox with the read-only additions `/opt/corsair-npm`, `/opt/yarn-v1.21.1` and `/lib64` (Debian buster is not merged-`/usr`; its loader lives there): exact `node`/`npm`/`yarn`/`jest` versions after an offline `npm ci` of the staged fixture, the Jest report, and the offline diagnostics of its siblings: missing package (`ENOTCACHED`), no discovery (`No tests found`), syntax (`Test suite failed to run` with `SyntaxError`) and assertion (`Expected: 2`/`Received: 1`). Because the five cases install their frameworks from the npm registry during setup (SPEC-0026), the gate also sets a policy letting `/usr/local/bin/node` GET one pinned tarball and one absent package name from `registry.npmjs.org`, then installs `is-number@7.0.0` through a lockfile with its SHA-512 (`npm ci`, real `require`) and requires an `E404` for the absent package that is neither a policy denial nor a TLS failure. Node 8 reads the sandbox CA from `NODE_EXTRA_CA_CERTS`; this step is the first live evidence that it does.

## Acceptance and validation

Offline: `make test-config` with `jest_report` rejection guards and `--toolchain node8` selection. Image-only checks in a container are recorded as image-only. Live on RIG0: `make toolchain-images TOOLCHAINS=node8`, `make toolchain-images-load TOOLCHAINS=node8` and `make qualify-toolchain TOOLCHAINS=node8` passing on a fresh admitted kind node, with every failed attempt kept in the qualification report. A real case runs only with the runner PR.

## Decisions and open questions

One image per runtime version (SPEC-0042); `buster-slim` rather than the full `buster` (Debian with build tools) to match the slim Python images; it can be revisited if a Node 8 case needs native addons. Node 8.17.0 because it is the last Node 8 release and the official image's final build; its row will claim `8.17.0` only. Jest 24.8.0 is the fixture because it is the framework of two of the five cases; the framework row and its range come with the runner. The upstream image is end of life (Node 8 EOL 2019-12-31, Debian buster EOL 2024-06-30): accepted because the cases declare it, and the sandbox, not the image, is the security boundary. Plan: [PLAN-0062](../plans/PLAN-0062-node8-toolchain.md).
