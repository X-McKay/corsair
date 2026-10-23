---
name: javascript-node-test
description: Write JavaScript differential probes using the built-in Node test runner and native line coverage. Use when the runtime is javascript / node-test.
---

# JavaScript / node:test

Use Node 22 and a CommonJS probe at `/work/.corsair/corsair_probe.cjs`. Export exactly the two payloads and a one-argument function:

```javascript
const CONTROL_PAYLOAD = 'benign';
const EXPLOIT_PAYLOAD = 'malicious';
async function run_target(payload) {
  const target = require('/work/path/to/target.cjs');
  const result = await target.operation(payload);
  return result.isSafe;
}
module.exports = { CONTROL_PAYLOAD, EXPLOIT_PAYLOAD, run_target };
```

- Read the reported file first. Use absolute `/work/...` imports: the probe lives in a separate directory.
- For ESM targets use `await import('/work/path/to/target.mjs')` inside the async function. A `.js` target follows its own package's `type` setting. The probe always stays `.cjs`.
- Await callbacks via a Promise or `node:util.promisify`. Unawaited work is not evidence.
- Call the real public seam and return the same boolean security invariant for both payloads: `true` means it held,
  `false` means the reported condition occurred. The kernel-owned driver performs the assertion. Do not assert in
  the probe; every exception thrown by the probe or application is an error, including `AssertionError`.
- Use `fs.mkdtempSync` under `os.tmpdir()` for fixtures and clean up in `finally`. The source tree is read-only, and probes have no network.
- The kernel supplies the test runner and JUnit/V8 coverage. Do not add `test()` calls, Jest, mocking libraries, reporters, or transpilers. Native collection validates the probe's exports and arity in the container; the host's symbol preflight is not a JavaScript parser.
- The runtime has no project dependencies initially. Use an empty build script for built-in modules, or `npm ci --ignore-scripts --no-audit --no-fund` when a checked-in lockfile supplies required dependencies. For a package without a lockfile, use `npm install --ignore-scripts --no-audit --no-fund` and record that weaker reproducibility.
- TypeScript and legacy Node 8 are unsupported. Do not rewrite the target or its security policy to make it run.
