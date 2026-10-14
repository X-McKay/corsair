---
name: probe-protocol
description: How every Corsair probe test reports its run to trusted code - the start and end marker files and the run token.
---
# Probe protocol

Trusted code runs your test alone, exactly once, with the framework's own runner, and reads only three facts:
the exit code, two marker files, and (for the exploit probe) whether the run token appears in the output. It
never parses a report. Your test makes those facts mean something by following these rules.

## Markers (both probes)

The environment variable `CORSAIR_MARKER_DIR` names a directory that exists when the test runs.

- The FIRST statement of the test body creates a file named `start` in that directory.
- The LAST statement of the test body, after every assertion, creates a file named `end` in that directory.
- Write them inside the test body itself, not in a fixture, setup or teardown hook, helper class or
  module-level code, and not inside a guard, loop or exception handler. Content does not matter; an empty file
  is enough. Use the language's standard library to read the variable and write the files.
- Nothing that can fail goes before `start`. Nothing goes after `end`.

So `start` without `end` means the body began but stopped early (an assertion failed or something raised), and
no `start` means the test never ran.

## Token (exploit probe only)

The environment variable `CORSAIR_TOKEN` holds a fresh random string for each run.

- Read it at run time and pass it as the failure message of the one security assertion, so the runner prints
  it exactly when that assertion fails.
- Use it nowhere else: never print, log, compare, hard-code, store or put it in another assertion or in an
  exception you raise yourself.
- The control probe never reads or mentions `CORSAIR_TOKEN`.

## One test, honestly failing

- The file holds exactly one test, with the planned name. Native parametrisation of that one test is allowed;
  every case then follows the same marker and token rules.
- Never catch the assertion failure, mark the test expected-to-fail, skip it, return early, retry, or exit the
  process yourself. A failing assertion must fail the test through the framework.
- Keep the test self-contained: no network, no dependence on other tests or their order, temporary files only
  in a temporary directory you create.
