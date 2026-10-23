# Node.js / TypeScript / Vite runtime

- Image: Debian-based **Node 22** with `c8` 10.1.3, TypeScript 5.7.3, `tsx` 4.19.2 and Vite 6.0.11 preinstalled under
  `/opt/corsair/node`. Their executables (`c8`, `tsx`, `tsc`, `vite`) are already on `PATH`. Python, `pytest` 9.0.3 and
  `coverage` 7.13.4 are also installed because the kernel's one-test Python driver owns the probe.
- The repository root is `/work`; the submitted Python probe is `/work/.corsair/corsair_probe.py`. It must define
  `CONTROL_PAYLOAD`, `EXPLOIT_PAYLOAD`, and a synchronous one-argument `run_target(payload)`. Start the real Node
  process from that function with `subprocess`; do not add a second test runner or mock the target.
- A JavaScript target can normally be launched with `node path/to/entry.js`. For TypeScript, use the trusted `tsx`
  executable, for example `tsx path/to/entry.ts`, or invoke the repository's already-built JavaScript. This avoids
  resolving `tsx` from project-controlled dependencies when using Node's `--import` flag. Verify the exact command in
  your working sandbox before submitting it. A Vite application is usually best exercised through its server-side
  module or built output, not a long-lived dev server.
- The build script runs once with network, then `/work` is sealed read-only and each payload runs offline as uid/gid
  `1000`. Install project dependencies during build replay (prefer `npm ci` when the repository lockfile supports it);
  the probe may write only `/tmp` and `/work/.corsair`.
- The kernel sets `NODE_V8_COVERAGE` to `/tmp/corsair/node/v8`, then renders it with its trusted `c8` after pytest
  exits. It accepts only c8's remapped LCOV entry for the exact `target_file`; Python coverage of the probe is never
  evidence for a JS or TS target. For TypeScript, select `target_lines` in the original `.ts` source and ensure source
  maps are enabled by the execution route.
- Keep one safety invariant for both payloads. Catch expected application exceptions in `run_target` when the invariant
  rather than the exception is what distinguishes the inputs; an assertion raised inside application code is not a
  demonstrated violation.
