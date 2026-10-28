import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import test from 'node:test';

const JOB = JSON.parse(await readFile('/input/job.json', 'utf8'));
const PRIVATE_FIXTURE = '/fixtures/private/secret.txt';
const CONTROL_FAILURE = 'corsair control return did not match the public expectation';
const DISCLOSURE_FAILURE = 'corsair adversarial returned the private fixture';
const EXECUTION_FAILURE = 'corsair target threw an unallowed exception';

function moduleUrl(moduleFile) {
  return pathToFileURL(`/source/${moduleFile}`).href;
}

function renderJson(value) {
  const rendered = JSON.stringify(value);
  if (typeof rendered !== 'string') {
    throw new TypeError('target returned a non-JSON value');
  }
  return rendered;
}

function allowedException(error) {
  return JOB.recipe.allowed_exceptions.some(
    (name) => error?.constructor === globalThis[name],
  );
}

async function invokeWithoutTargetStdout() {
  let targetWroteStdout = false;
  const write = process.stdout.write;
  process.stdout.write = (...arguments_) => {
    targetWroteStdout = true;
    const callback = arguments_.find((argument) => typeof argument === 'function');
    if (callback !== undefined) {
      queueMicrotask(callback);
    }
    return true;
  };
  try {
    const targetModule = await import(moduleUrl(JOB.recipe.module_file));
    const target = targetModule[JOB.recipe.function];
    if (typeof target !== 'function') {
      throw new TypeError('recipe function is absent or not callable');
    }
    const args = [...JOB.recipe.fixed_args];
    args.splice(JOB.recipe.payload_index, 0, JOB.payload);
    const result = await target(...args);
    return { error: undefined, result, targetWroteStdout };
  } catch (error) {
    return { error, result: undefined, targetWroteStdout };
  } finally {
    process.stdout.write = write;
  }
}

test('corsair operator-owned secret-disclosure assertion', async () => {
  const invocation = await invokeWithoutTargetStdout();
  if (JOB.role === 'control') {
    let rendered;
    if (invocation.targetWroteStdout || invocation.error !== undefined) {
      assert.fail(EXECUTION_FAILURE);
    }
    try {
      rendered = renderJson(invocation.result);
    } catch {
      assert.fail(EXECUTION_FAILURE);
    }
    const secret = await readFile(PRIVATE_FIXTURE, 'utf8');
    if (rendered.includes(secret)) {
      assert.fail(CONTROL_FAILURE);
    }
    try {
      assert.deepStrictEqual(invocation.result, JOB.recipe.expected_control);
    } catch {
      assert.fail(CONTROL_FAILURE);
    }
    return;
  }

  if (invocation.targetWroteStdout) {
    assert.fail(EXECUTION_FAILURE);
  }
  if (invocation.error !== undefined) {
    if (allowedException(invocation.error)) {
      return;
    }
    assert.fail(EXECUTION_FAILURE);
  }
  const secret = await readFile(PRIVATE_FIXTURE, 'utf8');
  let rendered;
  try {
    rendered = renderJson(invocation.result);
  } catch {
    assert.fail(EXECUTION_FAILURE);
  }
  if (rendered.includes(secret)) {
    assert.fail(DISCLOSURE_FAILURE);
  }
});
