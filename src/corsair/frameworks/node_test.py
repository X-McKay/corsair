"""JavaScript / node:test. Native V8 parsing and execution happen only inside the sandbox."""
from __future__ import annotations

from collections.abc import Mapping

from .base import PROBE_DIR, RESULT_DIR, WORKDIR, ProbeResult
from .reports import read_probe

DRIVER = r'''const { strictEqual } = require('node:assert');
const { test } = require('node:test');
const fs = require('node:fs');
const writeFileSync = fs.writeFileSync.bind(fs);
const stringify = JSON.stringify.bind(JSON);
const hasOwn = Object.hasOwn.bind(Object);
const TypeErrorClass = TypeError;
const string = String;
const role = process.env.CORSAIR_ROLE;
const resultPath = process.env.CORSAIR_RESULT;
const expected = role === 'control';
const probe = require('./corsair_probe.cjs');
const payloads = { control: probe.CONTROL_PAYLOAD, exploit: probe.EXPLOIT_PAYLOAD };

if (!hasOwn(probe, 'CONTROL_PAYLOAD') || !hasOwn(probe, 'EXPLOIT_PAYLOAD') ||
    typeof probe.run_target !== 'function' || probe.run_target.length !== 1) {
  throw new TypeErrorClass('Export CONTROL_PAYLOAD, EXPLOIT_PAYLOAD and run_target(payload) from the probe');
}

function record(result, invariant_held = null, error = null) {
  writeFileSync(resultPath, stringify({
    role, result, invariant_held,
    exception_type: error === null ? null : (error?.name || 'Error'),
    message: error === null ? null : string(error?.message ?? error).slice(0, 2000),
  }));
}

test(`test_probe[${role}]`, async () => {
  let invariant;
  try {
    invariant = await probe.run_target(payloads[role]);
    if (typeof invariant !== 'boolean') {
      throw new TypeErrorClass('run_target(payload) must return a boolean security invariant');
    }
  } catch (error) {
    record('ERROR', null, error);
    throw error;
  }
  const result = invariant === expected ? 'PASS' : 'FAIL';
  record(result, invariant);
  strictEqual(invariant, expected, 'security invariant did not match the role expectation');
});
'''

# node:test owns coverage measurement. Convert its native line counts into the shared report schema.
COVERAGE_REPORTER = r'''module.exports = async function* (source) {
  for await (const event of source) {
    if (event.type === 'test:coverage') {
      const files = {};
      for (const file of event.data.summary.files) {
        files[file.path] = { executed_lines: file.lines.filter(line => line.count > 0).map(line => line.line) };
      }
      yield JSON.stringify({ files });
    }
  }
};
'''


class NodeTest:
    name = "node-test"
    language = "javascript"
    target_suffixes = (".js", ".cjs", ".mjs")
    guidance = "javascript-node-test"
    probe_file = "corsair_probe.cjs"

    def guard(self, probe: str):
        from ..kernel import Gate, GateVerdict

        missing = [name for name in ("CONTROL_PAYLOAD", "EXPLOIT_PAYLOAD", "run_target", "module.exports")
                   if name not in probe]
        return GateVerdict(passed=not missing, stage=Gate.AST_GUARD,
                           reason=f"probe must export {', '.join(missing)}" if missing else
                                  "symbol preflight passed; native parsing and export validation run in the container")

    def driver_files(self) -> dict[str, bytes]:
        return {"test_corsair_probe.cjs": DRIVER.encode(), "coverage-reporter.cjs": COVERAGE_REPORTER.encode()}

    def command(self, role: str, target_file: str) -> list[str]:
        # Node's include option is a glob. Measure /work and let read_probe match the literal target path.
        return ["node", "--test", "--experimental-test-coverage", f"--test-coverage-include={WORKDIR}/**",
                "--test-reporter=junit", f"--test-reporter-destination={RESULT_DIR}/junit.xml",
                f"--test-reporter={PROBE_DIR}/coverage-reporter.cjs",
                f"--test-reporter-destination={RESULT_DIR}/coverage.json", f"{PROBE_DIR}/test_corsair_probe.cjs"]

    def post_command(self, role: str, target_file: str) -> None:
        return None

    def environment(self, role: str) -> Mapping[str, str]:
        return {"CORSAIR_ROLE": role, "CORSAIR_RESULT": f"{RESULT_DIR}/result.json", "HOME": "/tmp",
                "NODE_OPTIONS": "", "NODE_V8_COVERAGE": f"{RESULT_DIR}/v8"}

    def result_paths(self) -> list[str]:
        return [f"{RESULT_DIR}/result.json", f"{RESULT_DIR}/junit.xml", f"{RESULT_DIR}/coverage.json"]

    def read(self, files: Mapping[str, bytes | None], hypothesis, role: str, source=None) -> ProbeResult:
        return read_probe(files, hypothesis, role)
