---
name: differential-probing
description: Design a differential vulnerability probe with two payloads and one invariant. Read before submitting any probe to the kernel.
---

# Differential probing

One probe module, two payloads, one invariant. The kernel verifies it; you cannot argue with the kernel, only fix
the probe.

## Contract

Read the selected runtime skill for syntax, imports and dependency setup. Python, JavaScript, Java and Perl all
implement the same security contract; the kernel supplies the native driver. Python expresses failure with its own
assertion. The other runtimes return the invariant as a boolean and let the driver assert it.

```python
CONTROL_PAYLOAD = ...   # a benign input the target must handle correctly
EXPLOIT_PAYLOAD = ...   # an input that makes the reported condition occur on vulnerable code

def run_target(payload) -> None:
    # 1. build the smallest fixture the call needs (tempfile.TemporaryDirectory, in-memory objects)
    # 2. call the REAL target through its public seam with the payload
    # 3. assert the security invariant; the assertion message says what was observed
```

Rules the kernel enforces, so write to them:

- `run_target` applies the same code path and the same assertion to both payloads. Never compare the payload to
  `CONTROL_PAYLOAD` or `EXPLOIT_PAYLOAD`, never branch on which one you got.
- The control run must pass **and** execute the hypothesis' `target_lines`. If it does not reach them, your
  hypothesis names the wrong lines or your fixture bypasses the target.
- The exploit run must violate the invariant. In Python, this means **your** `assert` raises `AssertionError` in
  the probe. In JavaScript and Java, `run_target` returns `false`; Perl returns a false scalar. A true value means
  the invariant held. A `TypeError`,
  `FileNotFoundError`, or any exception from inside the application is `errored`, not a demonstration. Catch
  expected exceptions from the target when the invariant is about what happens afterwards (for example "the
  outside file was not opened"), and let the invariant decide.
- Both vulnerable runs must execute every declared target line. Both fixed runs must execute the target file;
  line numbers may shift in a fix. Missing coverage cannot verify a fix.
- No mocking or runtime-replacement library named by the selected runtime skill. If a dependency must be
  controlled, pass a real object through the target's own parameters; never replace the function that owns the
  security property.
- The repository root is `/work`. Load the target the way its own tests do, following the selected runtime skill.
- The attacker controls only the payload. The probe runs unprivileged with no network: it cannot edit `/etc/hosts`,
  change name resolution, rewrite the target's allowlists or settings, or stand in for an allowlisted host. A
  check that neutralises the payload under that model is a result, not an obstacle: submit the strongest payload
  and let the exploit gate say the invariant held.

## Invariant patterns by condition

| Condition | Invariant the exploit violates |
| --- | --- |
| Path traversal | resolved path is relative to the allowed root; or the outside sentinel content is never returned / never opened |
| Command / argument injection | a sentinel file the payload would create does not exist; or the executed argv contains the payload as one argument |
| SQL injection | the query returned only the rows the benign filter admits; or the parameter stayed data (count of rows, not count of tables) |
| SSRF / open redirect | the resolved host or location stays within the allowed set |
| Deserialization / code injection | a sentinel side effect (file, env var, global) was not produced |
| Missing authorization | the protected operation returns the denied result for the unprivileged principal |

Make the sentinel yours: create it in the fixture, check it after the call. Do not assert on log text.

## Hypothesis

`target_file` is relative to the repository root. `target_lines` are the lines where the flaw lives (the sink call
and the missing or wrong check), 1-based, as in the file you read with `bash`. `expected_violation` says what the
assertion observes on exploit, in one sentence.

## Build script

Bash, run once in a clean container from the repository root with network, before the network is removed. Follow
the selected runtime skill and `build-recipes`; leave it empty for a plain module tree. Never fetch or run code the
probe does not need.
