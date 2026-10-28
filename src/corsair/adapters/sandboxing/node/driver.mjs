#!/usr/bin/env node
/**
 * Trusted in-image driver for the JavaScript secret-disclosure recipe.
 *
 * The operator creates a JSON-only job. This driver writes no target code and invokes
 * Node's native node:test runner against the fixed ESM probe. Target output stays in
 * native report files; stdout receives exactly one sanitized corsair.driver/1 record.
 *
 * The target remains arbitrary JavaScript in a constrained container. This is evidence
 * of the fixed assertion under that boundary, not a claim of hostile-runtime, kernel,
 * daemon, or dependency-build integrity.
 */

import { readFile } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import path from 'node:path';

const JOB_PATH = '/input/job.json';
const WORK = '/work';
const JUNIT = path.join(WORK, 'junit.xml');
const COVERAGE = path.join(WORK, 'coverage.lcov');
const PROBE = '/opt/corsair/probe.test.mjs';
const SCHEMA_VERSION = 'corsair.driver/1';
const JOB_SCHEMA_VERSION = 'corsair.driver-job/1';
const ALLOWED_EXCEPTION_NAMES = new Set(['Error', 'TypeError', 'RangeError']);
const RESULT_MARKERS = {
  control: 'corsair control return did not match the public expectation',
  disclosure: 'corsair adversarial returned the private fixture',
  execution: 'corsair target threw an unallowed exception',
};

function emptyJunit(status = 'INVALID') {
  return { status, tests: 0, failures: 0, errors: 0, skipped: 0 };
}

function invalidRecord() {
  return {
    schema_version: SCHEMA_VERSION,
    operation_id: '',
    role: '',
    source_digest: '',
    submission_digest: '',
    native_exit_code: 2,
    outcome: 'INVALID',
    observation_kind: 'execution_error',
    target_executed: false,
    covered_lines: [],
    coverage_file: '',
    junit: emptyJunit(),
  };
}

function isPlainObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function isJsonValue(value, depth = 0) {
  if (depth > 32 || value === null || typeof value === 'string' || typeof value === 'boolean') {
    return depth <= 32 && (value === null || typeof value !== 'number' || Number.isFinite(value));
  }
  if (typeof value === 'number') {
    return Number.isFinite(value);
  }
  if (Array.isArray(value)) {
    return value.length <= 256 && value.every((item) => isJsonValue(item, depth + 1));
  }
  if (isPlainObject(value)) {
    return (
      Object.keys(value).length <= 256
      && Object.values(value).every((item) => isJsonValue(item, depth + 1))
    );
  }
  return false;
}

function isSafePath(value) {
  return (
    typeof value === 'string'
    && value.length > 0
    && value.length <= 1024
    && !value.startsWith('/')
    && value.split('/').every((part) => part !== '' && part !== '.' && part !== '..')
  );
}

function isPublicIdentifier(value) {
  return typeof value === 'string' && /^[A-Za-z][A-Za-z0-9_$]*$/.test(value) && !value.startsWith('_');
}

function isDigest(value) {
  return typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
}

function isIdentifier(value) {
  return typeof value === 'string' && /^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$/.test(value);
}

function hasOnlyKeys(value, keys) {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
}

function safeJob(value) {
  const jobKeys = [
    'schema_version',
    'operation_id',
    'role',
    'source_digest',
    'submission_digest',
    'recipe',
    'payload',
  ];
  const recipeKeys = [
    'kind',
    'module_file',
    'function',
    'fixed_args',
    'payload_index',
    'public_files',
    'expected_control',
    'private_fixture_path',
    'allowed_exceptions',
  ];
  if (
    !isPlainObject(value)
    || !hasOnlyKeys(value, jobKeys)
    || value.schema_version !== JOB_SCHEMA_VERSION
    || !isIdentifier(value.operation_id)
    || !['control', 'adversarial'].includes(value.role)
    || !isDigest(value.source_digest)
    || !isDigest(value.submission_digest)
    || !isJsonValue(value.payload)
    || !isPlainObject(value.recipe)
    || !hasOnlyKeys(value.recipe, recipeKeys)
  ) {
    throw new TypeError('invalid job');
  }
  const { recipe } = value;
  if (
    recipe.kind !== 'javascript.secret_disclosure/1'
    || recipe.private_fixture_path !== '/fixtures/private/secret.txt'
    || !isSafePath(recipe.module_file)
    || !recipe.module_file.endsWith('.mjs')
    || !isPublicIdentifier(recipe.function)
    || !Array.isArray(recipe.fixed_args)
    || recipe.fixed_args.length > 16
    || !recipe.fixed_args.every((item) => isJsonValue(item))
    || !Number.isInteger(recipe.payload_index)
    || recipe.payload_index < 0
    || recipe.payload_index > recipe.fixed_args.length
    || !isPlainObject(recipe.public_files)
    || Object.keys(recipe.public_files).length > 16
    || !Object.entries(recipe.public_files).every(
      ([name, content]) => isSafePath(name) && typeof content === 'string' && content.length <= 65536,
    )
    || !isJsonValue(recipe.expected_control)
    || !Array.isArray(recipe.allowed_exceptions)
    || recipe.allowed_exceptions.length > 3
    || new Set(recipe.allowed_exceptions).size !== recipe.allowed_exceptions.length
    || !recipe.allowed_exceptions.every((name) => ALLOWED_EXCEPTION_NAMES.has(name))
  ) {
    throw new TypeError('invalid job');
  }
  return value;
}

function runNativeTest() {
  const command = [
    '--test',
    '--test-isolation=none',
    '--experimental-test-coverage',
    '--test-reporter=junit',
    `--test-reporter-destination=${JUNIT}`,
    '--test-reporter=lcov',
    `--test-reporter-destination=${COVERAGE}`,
    PROBE,
  ];
  return new Promise((resolve) => {
    let child;
    try {
      child = spawn(process.execPath, command, {
        cwd: WORK,
        env: {
          HOME: '/tmp',
          PATH: process.env.PATH ?? '',
          NODE_NO_WARNINGS: '1',
        },
        stdio: ['ignore', 'ignore', 'ignore'],
      });
    } catch {
      resolve(2);
      return;
    }
    child.once('error', () => resolve(2));
    child.once('exit', (code) => resolve(Number.isInteger(code) ? code : 2));
  });
}

function junitProjection(document, exitCode) {
  if (
    !document.startsWith('<?xml version="1.0" encoding="utf-8"?>\n<testsuites>\n')
    || !document.endsWith('</testsuites>\n')
  ) {
    return { valid: false, junit: emptyJunit() };
  }
  const cases = document.match(/<testcase\b[^>]*\/?>(?:[\s\S]*?<\/testcase>)?/g) ?? [];
  if (cases.length !== 1 || !cases[0].includes('name="corsair operator-owned secret-disclosure assertion"')) {
    return { valid: false, junit: emptyJunit() };
  }
  const testCase = cases[0];
  const failures = (testCase.match(/<failure\b/g) ?? []).length;
  const errors = (testCase.match(/<error\b/g) ?? []).length;
  const skipped = (testCase.match(/<skipped\b/g) ?? []).length;
  const counts = { tests: 1, failures, errors, skipped };
  if (failures + errors + skipped > 1) {
    return { valid: false, junit: { status: 'INVALID', ...counts } };
  }
  if (exitCode === 0 && failures === 0 && errors === 0 && skipped === 0) {
    return { valid: true, junit: { status: 'PASS', ...counts }, testCase };
  }
  if (exitCode !== 0 && failures === 1 && errors === 0 && skipped === 0) {
    return { valid: true, junit: { status: 'FAILURE', ...counts }, testCase };
  }
  if (exitCode !== 0 && errors === 1 && failures === 0 && skipped === 0) {
    return { valid: true, junit: { status: 'ERROR', ...counts }, testCase };
  }
  return { valid: false, junit: { status: 'INVALID', ...counts } };
}

async function readJunit(exitCode) {
  try {
    return junitProjection(await readFile(JUNIT, 'utf8'), exitCode);
  } catch {
    return { valid: false, junit: emptyJunit() };
  }
}

async function coverageLines(moduleFile) {
  const expected = `../source/${moduleFile}`;
  try {
    const lines = (await readFile(COVERAGE, 'utf8')).split(/\r?\n/);
    const covered = new Set();
    let matchingSource = false;
    let complete = false;
    for (const line of lines) {
      if (line.startsWith('SF:')) {
        matchingSource = line.slice(3) === expected;
      } else if (line === 'end_of_record') {
        if (matchingSource) {
          complete = true;
        }
        matchingSource = false;
      } else if (matchingSource && line.startsWith('DA:')) {
        const match = /^DA:([1-9][0-9]*),([0-9]+)$/.exec(line);
        if (match === null) {
          return [];
        }
        if (Number(match[2]) > 0) covered.add(Number(match[1]));
      }
    }
    return complete && covered.size > 0 ? [...covered].sort((left, right) => left - right) : [];
  } catch {
    return [];
  }
}

function hasMarker(testCase, marker) {
  return typeof testCase === 'string' && testCase.includes(marker);
}

function recordFor(job, exitCode, projection, coveredLines) {
  let outcome = 'ERROR';
  let observationKind = 'execution_error';
  let targetExecuted = false;
  let junit = projection.junit;
  if (projection.valid && coveredLines.length > 0) {
    if (junit.status === 'PASS') {
      outcome = 'PROPERTY_HELD';
      observationKind = 'held';
      targetExecuted = true;
    } else if (job.role === 'control' && hasMarker(projection.testCase, RESULT_MARKERS.control)) {
      outcome = 'INVALID';
      observationKind = 'invalid_control';
      targetExecuted = true;
      junit = { ...junit, status: 'INVALID' };
    } else if (job.role === 'adversarial' && hasMarker(projection.testCase, RESULT_MARKERS.disclosure)) {
      outcome = 'VIOLATION';
      observationKind = 'disclosure';
      targetExecuted = true;
    } else {
      junit = { ...junit, status: 'ERROR' };
    }
  } else {
    junit = { ...junit, status: 'ERROR' };
  }
  return {
    schema_version: SCHEMA_VERSION,
    operation_id: job.operation_id,
    role: job.role,
    source_digest: job.source_digest,
    submission_digest: job.submission_digest,
    native_exit_code: exitCode,
    outcome,
    observation_kind: observationKind,
    target_executed: targetExecuted,
    covered_lines: coveredLines,
    coverage_file: job.recipe.module_file,
    junit,
  };
}

async function main() {
  let job;
  try {
    job = safeJob(JSON.parse(await readFile(JOB_PATH, 'utf8')));
  } catch {
    process.stdout.write(`${JSON.stringify(invalidRecord())}\n`);
    return 2;
  }
  const exitCode = await runNativeTest();
  const [projection, coveredLines] = await Promise.all([
    readJunit(exitCode),
    coverageLines(job.recipe.module_file),
  ]);
  const nativeReports = {};
  for (const [name, file] of [['junit', JUNIT], ['coverage', COVERAGE]]) {
    try {
      const report = await readFile(file, 'utf8');
      if (Buffer.byteLength(report) <= 32768) nativeReports[name] = report;
    } catch { /* Missing native reports remain explicit in the projected ERROR record. */ }
  }
  process.stdout.write(`${JSON.stringify({ ...recordFor(job, exitCode, projection, coveredLines), native_reports: nativeReports })}\n`);
  return exitCode;
}

process.exitCode = await main();
