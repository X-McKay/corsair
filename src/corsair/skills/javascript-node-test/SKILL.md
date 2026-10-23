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
- For a repository-local CLI, use `execFileSync(process.execPath, ['/work/path/to/cli.cjs', payload],
  {cwd: '/work', encoding: 'utf8', timeout: ...})` or an awaited equivalent. Omit `env`, or extend it with
  `{...process.env, ...applicationChanges}` so `NODE_V8_COVERAGE` is inherited. Wait for completion. The adapter
  unions raw parent and child reports by literal file URL/path, including spaces and brackets; launcher or decoy
  coverage is insufficient. Unknown child failures must throw. Convert only a documented refusal into `true`
  through the same invariant.
- Call the real public seam using the same setup and target call for both payloads, and return the same Boolean
  invariant: `true` means preserved, `false` means the reported condition occurred. The driver assigns control
  `PASS` for true and exploit `PASS` for false; exploit `FAIL` is a clean true observation and scoped negative
  evidence. Return a primitive boolean; strings, Boolean objects and arbitrary truthy values are invalid. The probe
  receives no role or expected answer. Every uncaught exception is `ERROR`, including `AssertionError`; do not assert
  in the probe. Repository-local script or CLI execution requires native coverage of the child target lines;
  stdout and exit status alone cannot satisfy the coverage gate.
- Use `fs.mkdtempSync` under `os.tmpdir()` for fixtures and clean up in `finally`. The source tree is read-only, and probes have no network.
- The kernel supplies the test runner and JUnit/V8 coverage. Do not add `test()` calls, Jest, mocking libraries, reporters, or transpilers. Native collection validates the probe's exports and arity in the container; the host's symbol preflight is not a JavaScript parser.
- The runtime has no project dependencies initially. Use an empty build script for built-in modules, or `npm ci --ignore-scripts --no-audit --no-fund` when a checked-in lockfile supplies required dependencies. For a package without a lockfile, use `npm install --ignore-scripts --no-audit --no-fund` and record that weaker reproducibility.
- TypeScript and legacy Node 8 are unsupported. Do not rewrite the target or its security policy to make it run.
