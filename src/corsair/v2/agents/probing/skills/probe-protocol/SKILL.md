---
name: probe-protocol
description: How every Corsair probe test reports its run to trusted code - the start, check and end marker files and the run token.
---
# Probe protocol

Trusted code runs your test alone, exactly once, with the framework's own runner, and reads only four facts: the
exit code, three marker files, and whether the run token appears in the output. It never parses a report. Both
probes, control and exploit, follow the same rules.

## Markers

The environment variable `CORSAIR_MARKER_DIR` names a directory that exists when the test runs.

- The FIRST statement of the test body creates a file named `start` in that directory (content does not matter).
- IMMEDIATELY BEFORE the main assertion, the test writes a file named `check` whose content is `safe` when the
  asserted property holds and `unsafe` when it does not. Compute it from the very same condition the assertion
  checks: evaluate the condition once into a variable, write `check` from that variable, then assert that
  variable. Never hard-code `safe` or `unsafe`, and never compute `check` from anything else.
- The LAST statement of the test body, after every assertion, creates a file named `end` (content does not
  matter).
- Write them inside the test body itself, not in a fixture, setup or teardown hook, helper class or module-level
  code, and not inside a guard, loop or exception handler. Use the language's standard library.
- Nothing that can fail goes before `start`. Nothing goes after `end`.

So `start` without `check` means the body began but raised before reaching its assertion; `check` = `unsafe`
without `end` means the assertion failed; no `start` means the test never ran.

## Token

The environment variable `CORSAIR_TOKEN` holds a fresh random string for each run.

- Read it at run time and pass it as the failure message of the one main assertion (the one right after
  `check`), so the runner prints it exactly when that assertion fails.
- Use it nowhere else: never print, log, compare, hard-code, store or put it in another assertion or in an
  exception you raise yourself.

## One test, honestly failing

- The file holds exactly one test, with the planned name. Native parametrisation of that one test is allowed;
  every case then follows the same marker and token rules.
- Never catch the assertion failure, mark the test expected-to-fail, skip it, return early, retry, or exit the
  process yourself. A failing assertion must fail the test through the framework.
- Keep the test self-contained: no network, no dependence on other tests or their order, temporary files only
  in a temporary directory you create.

## If your draft comes back once

Trusted code runs each frozen draft once before review, as a mechanical check only. If the test never started
or raised before its `check` marker, you get one chance to revise it, with only the result class, a fixed hint
and, where the framework has one, the output of a syntax check on your file. You never see the run's output or
whether your assertion held.
