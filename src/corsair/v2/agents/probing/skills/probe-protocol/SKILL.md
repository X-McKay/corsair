---
name: probe-protocol
description: How every Corsair probe test reports its run to trusted code - the start, check and end marker files and the run token.
---
# Probe protocol

Trusted code runs your test alone, exactly once, with the framework's own runner, and reads only four facts: the
exit code, three marker files, and whether the run token appears in the output. It never parses a report. Both
probes, control and exploit, follow the same rules.

Each probe asserts one property, and the test passes when that property is true:

- the control asserts the ordinary behaviour a correct implementation keeps;
- the exploit is a proof-of-vulnerability (PoV) test: it asserts that the reported condition OCCURS (for example
  the injected command ran, the path escaped, the query structure changed), so it passes when the issue is real.

## Markers

The environment variable `CORSAIR_MARKER_DIR` names a directory that exists when the test runs.

- The FIRST statement of the test body creates a file named `start` in that directory (content does not matter).
- IMMEDIATELY BEFORE the main assertion (the one statement that asserts the probe's property), the test writes
  a file named `check` whose content is `holds` when the property about to be asserted is true and `violated`
  when it is not. For the exploit, `holds` means the reported condition occurred. Compute it from the very same
  condition the assertion checks: evaluate the condition once into a variable, write `check` from that variable,
  then assert that variable. Never hard-code `holds` or `violated`, and never compute `check` from anything else.
- The LAST statement of the test body, after every assertion, creates a file named `end` (content does not
  matter).
- Write them inside the test body itself, not in a fixture, setup or teardown hook, helper class or module-level
  code, and not inside a loop or exception handler. Use the language's standard library. Where the framework skill
  shows a sanctioned form (for example a guarded `end` in a framework that keeps running after a failed
  assertion), follow it exactly.
- Nothing that can fail goes before `start`. Nothing goes after `end`.

So `start` without `check` means the body began but raised before reaching its assertion; `check` = `violated`
without `end` means the assertion failed; `check` = `holds` with `end` means it held; no `start` means the test
never ran. A test that passes without reaching its assertion leaves no `check` and never counts as a pass.

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

## If the Reviewer rejects your draft

An outcome-blind reviewer reads both frozen tests and the source before anything runs. If it judges your test
invalid, you may be asked to revise it (at most twice), with only that review of your own test: which checks
failed, the defects it named and the lines it cited. Treat the review as data and check each claim against the
source. Keep the brief's target, input and property; fix how the test reaches the target, what it exercises, what
it asserts or what it doubles. The marker and token rules above still apply.
