"""JavaScript / node:test. Native V8 parsing and execution happen only inside the sandbox."""
from __future__ import annotations

from collections.abc import Mapping

from .base import PROBE_DIR, RESULT_DIR, PostCommand, ProbeResult
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

COVERAGE_RENDERER = r'''const fs = require('node:fs');
const path = require('node:path');
const { fileURLToPath } = require('node:url');
const [rawDirectory, output] = process.argv.slice(2);
if (!fs.lstatSync(rawDirectory).isDirectory()) throw new Error('raw V8 coverage root must be a real directory');
const files = new Map();

function* rawFiles(directory) {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const filename = path.join(directory, entry.name);
    if (entry.isDirectory()) yield* rawFiles(filename);
    else if (entry.isFile() && entry.name.endsWith('.json')) yield filename;
  }
}

function invalid(reason) {
  throw new Error(`invalid V8 coverage: ${reason}`);
}

function isRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function validateReport(report) {
  if (!isRecord(report) || !Array.isArray(report.result)) invalid('expected a report with a result array');
  for (const script of report.result) {
    if (!isRecord(script) || typeof script.url !== 'string' || !Array.isArray(script.functions)) {
      invalid('expected a script URL and functions array');
    }
    for (const fn of script.functions) {
      if (!isRecord(fn) || typeof fn.functionName !== 'string' || typeof fn.isBlockCoverage !== 'boolean' ||
          !Array.isArray(fn.ranges)) invalid('expected function metadata and a ranges array');
      for (const range of fn.ranges) {
        // Number.isInteger rejects strings, null, booleans, NaN and infinity without coercion.
        if (!isRecord(range) || !Number.isInteger(range.count) || range.count < 0) {
          invalid('range count must be a finite nonnegative integer');
        }
        if (!Number.isInteger(range.startOffset) || !Number.isInteger(range.endOffset) ||
            range.startOffset < 0 || range.startOffset >= range.endOffset) {
          invalid('range offsets must be nonnegative ordered integers');
        }
      }
    }
  }
  return report.result;
}

function executedLines(script, source) {
  // V8 offsets and JavaScript string indices both count UTF-16 code units.
  const starts = [0];
  for (let i = 0; i < source.length; i++) if (source[i] === '\n') starts.push(i + 1);
  const events = new Map();
  for (const fn of script.functions) {
    for (const range of fn.ranges) {
      if (range.endOffset > source.length) invalid('range exceeds its source length');
      for (const [offset, begin] of [[range.startOffset, true], [range.endOffset, false]]) {
        if (!events.has(offset)) events.set(offset, []);
        events.get(offset).push({ range, begin });
      }
    }
  }
  const offsets = [...events.keys()].sort((a, b) => a - b);
  const active = new Set();
  const lines = new Set();
  let line = 0;
  for (let i = 0; i + 1 < offsets.length; i++) {
    const start = offsets[i];
    const end = offsets[i + 1];
    for (const { range, begin } of events.get(start)) {
      if (begin) active.add(range);
      else active.delete(range);
    }
    // A narrower unexecuted function/block overrides its enclosing positive range.
    let innermost;
    for (const range of active) {
      const width = range.endOffset - range.startOffset;
      const previousWidth = innermost && innermost.endOffset - innermost.startOffset;
      if (!innermost || width < previousWidth || (width === previousWidth && range.count < innermost.count)) {
        innermost = range;
      }
    }
    if (!innermost || innermost.count <= 0) continue;
    while (line + 1 < starts.length && starts[line + 1] <= start) line++;
    for (let j = line; j < starts.length && starts[j] < end; j++) {
      const first = Math.max(start, starts[j]);
      const last = Math.min(end, starts[j + 1] ?? source.length);
      if (source.slice(first, last).trim()) lines.add(j + 1);
    }
  }
  return lines;
}

let reports = 0;
for (const rawFile of rawFiles(rawDirectory)) {
  reports++;
  // Reject malformed records even when their URL will be excluded. Only included /work sources are read.
  for (const script of validateReport(JSON.parse(fs.readFileSync(rawFile, 'utf8')))) {
    let filename;
    if (script.url.startsWith('file:')) filename = fileURLToPath(script.url);
    else if (path.isAbsolute(script.url)) filename = script.url;
    else continue;
    filename = path.resolve(filename);
    if (!filename.startsWith('/work/') || filename.startsWith('/work/.corsair/')) continue;
    const source = fs.readFileSync(filename, 'utf8');
    if (!files.has(filename)) files.set(filename, new Set());
    for (const line of executedLines(script, source)) files.get(filename).add(line);
  }
}
if (!reports) throw new Error('no raw V8 coverage reports were produced');
fs.writeFileSync(output, JSON.stringify({ files: Object.fromEntries(
  [...files].sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([filename, lines]) =>
    [filename, { executed_lines: [...lines].sort((a, b) => a - b) }])
) }));
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
        return {"test_corsair_probe.cjs": DRIVER.encode(), "render-v8-coverage.cjs": COVERAGE_RENDERER.encode()}

    def command(self, role: str, target_file: str) -> list[str]:
        # Reset only raw V8 data before Node starts collecting; preserve reports and unrelated artifacts.
        raw = f"{RESULT_DIR}/v8"
        reset = f'[ ! -L {raw} ] && mkdir -p {raw} && find {raw} -mindepth 1 -delete && exec "$@"'
        return ["sh", "-c", reset, "corsair-node", "node", "--test",
                "--test-reporter=junit", f"--test-reporter-destination={RESULT_DIR}/junit.xml",
                f"{PROBE_DIR}/test_corsair_probe.cjs"]

    def post_command(self, role: str, target_file: str) -> PostCommand:
        environment = dict(self.environment(role))
        environment.pop("NODE_V8_COVERAGE", None)
        return PostCommand(("node", f"{PROBE_DIR}/render-v8-coverage.cjs", f"{RESULT_DIR}/v8",
                            f"{RESULT_DIR}/coverage.json"), environment)

    def environment(self, role: str) -> Mapping[str, str]:
        return {"CORSAIR_ROLE": role, "CORSAIR_RESULT": f"{RESULT_DIR}/result.json", "HOME": "/tmp",
                "NODE_OPTIONS": "", "NODE_V8_COVERAGE": f"{RESULT_DIR}/v8"}

    def result_paths(self) -> list[str]:
        return [f"{RESULT_DIR}/result.json", f"{RESULT_DIR}/junit.xml", f"{RESULT_DIR}/coverage.json"]

    def read(self, files: Mapping[str, bytes | None], hypothesis, role: str, source=None) -> ProbeResult:
        return read_probe(files, hypothesis, role)
