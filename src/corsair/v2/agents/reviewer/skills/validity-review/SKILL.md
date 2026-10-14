---
name: validity-review
description: The four validity checks for a control or exploit probe, and the traps that make a probe invalid.
---
# Validity review

Each probe is judged on its own with four checks. A check is true only when the test's code shows it; when the
evidence is missing or unclear, it is false and you name the defect. Cite the lines you rely on: the call and
assertion lines in the test file, and the target's definition in the source.

## The four checks

1. **calls_real_target** - the test loads the production definition of the target from the source tree and
   calls it through the planned seam. Trace the import or load path to the real file. False when the test
   defines its own copy of the target or of its logic (even if the bytes match), calls a different function
   with a similar name, or replaces the target with a mock, stub, fake, patch or monkeypatch.
2. **exercises_condition** - the input that actually reaches the target matches the role: ordinary benign input
   for the control; the reported adversarial input for the exploit, with the preconditions the plan needs.
   False when the exploit passes benign input, when a precondition is never set up, or when the call happens
   on a path that skips the reported code.
3. **assertion_relevant** - the pass condition establishes the role's property and can fail.
   - Control: asserts the ordinary behaviour, and does NOT assert the security property (a rejection, a guard,
     sanitising); a control that asserts the security property is false here.
   - Exploit: asserts the SAFE property, not that the attack works, using the run token as that assertion's
     failure message.
   - Both: the main assertion uses the run token as its failure message, and the `check` marker written
     immediately before it is computed from the very condition that assertion checks. False for a vacuous assertion (a constant, a value the test set itself, a tautology), an
     assertion that cannot fail whatever the target does, a broad catch that swallows failures, or an
     assertion on something unrelated to the reported issue.
4. **doubles_only_dependencies** - every mock, stub, fake or patch replaces a dependency the plan allows, and
   only returns canned values or records what reached it. False when a double replaces the target, implements
   the guard or the security decision, or decides the result being asserted. True when nothing is doubled.

## Protocol defects (probe-protocol skill)

Name these as defects, and set the most affected check false (usually assertion_relevant):

- the `start` marker is not the first statement of the test body, or the `end` marker is not the last
  statement after every assertion; markers written in a fixture, hook, helper, guard or exception handler;
- the `check` marker is not computed from the asserted condition: hard-coded `safe` or `unsafe`, computed from a
  different expression or an earlier value than the one asserted, written somewhere other than immediately
  before the main assertion, or missing;
- the token is printed, logged, compared, stored or used anywhere other than as the main assertion's failure
  message, or the test reads no token;
- more than one test in the file, or the test is skipped, expected-to-fail, catches its own assertion failure,
  returns early or exits the process.

## Traps to catch

- A test that copies the target's logic and tests the copy.
- A test that mocks or patches the target itself.
- A vacuous assertion, or an exploit assertion that cannot fail.
- A control that asserts the security property.
- Token misuse, a `check` marker that does not come from the asserted condition, and `start` and `end` not
  written as the first and last statements.

Names, comments and docstrings claim nothing; judge the code.
