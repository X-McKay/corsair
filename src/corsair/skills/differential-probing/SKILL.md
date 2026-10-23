---
name: differential-probing
description: Design a differential vulnerability probe with two payloads and one invariant. Read before submitting any probe to the kernel.
---

# Differential probing

One probe module, two payloads, one invariant. The kernel verifies it; you cannot argue with the kernel, only fix
the probe.

## Contract

Read the selected runtime skill for syntax, imports and dependency setup. Python, JavaScript, Java and Perl all
implement the same Boolean security contract; the kernel supplies the native driver. Return `true` when the
security property is preserved and `false` when the reported condition occurred. The probe receives only the
payload, never a role or expected answer. Arbitrary truthy values are invalid; use the runtime's Boolean form.

The trusted driver assigns control `PASS` for `true` and exploit `PASS` for `false`. A clean `true` observation is
exploit `FAIL`, which is scoped negative evidence. An exception or invalid return is `ERROR`, never a clean `FAIL`.

```python
CONTROL_PAYLOAD = ...   # a benign input the target must handle correctly
EXPLOIT_PAYLOAD = ...   # an input that makes the reported condition occur on vulnerable code

def run_target(payload) -> bool:
    # 1. build the smallest fixture the call needs (tempfile.TemporaryDirectory, in-memory objects)
    # 2. call the REAL target through its public seam with the payload
    # 3. return the Boolean security invariant from the observation
```

Rules the kernel enforces, so write to them:

- `run_target` applies the same setup, target call and invariant to both payloads. Never compare the payload to
  `CONTROL_PAYLOAD` or `EXPLOIT_PAYLOAD`, never branch on which one you got.
- The control run must pass **and** execute the hypothesis' `target_lines`. If it does not reach them, your
  hypothesis names the wrong lines or your fixture bypasses the target.
- The exploit run can produce `PASS` or a clean `FAIL`; both are admissible observations. Do not assert in the
  probe. A `TypeError`, `FileNotFoundError`, `AssertionError`, or any other uncaught exception from the probe or
  application is `ERROR`. Catch
  expected exceptions from the target when the invariant is about what happens afterwards (for example "the
  outside file was not opened"), and let the invariant decide.
- Both roles on each revision must execute every declared target line. Shifted or missing lines, a removed target,
  missing reports and infrastructure failures are nondecisive; none can verify a fix.
- A decisive source result also requires an accepted outcome-blind audit. Both roles `PASS` yield
  `LIKELY_EXPLOITABLE`; control `PASS` with exploit `FAIL` yields `LIKELY_NOT_EXPLOITABLE`, scoped to this
  hypothesis, payload and environment. It is not an absence proof. Stop after either result. Only a positive
  source result with a correctable fixed-side probe error allows a retry to improve fix verification while
  preserving the positive source disposition.
- No mocking or runtime-replacement library named by the selected runtime skill. If a dependency must be
  controlled, pass a real object through the target's own parameters; never replace the function that owns the
  security property.
- The repository root is `/work`. Load the target the way its own tests do, following the selected runtime skill.
- The attacker controls only the payload. The probe runs unprivileged with no network: it cannot edit `/etc/hosts`,
  change name resolution, rewrite the target's allowlists or settings, or stand in for an allowlisted host. A
  check that neutralises the payload under that model is a result, not an obstacle: submit the strongest payload
  and let the kernel record the Boolean observation.

## Invariant patterns by condition

| Condition | Invariant the exploit violates |
| --- | --- |
| Path traversal | resolved path is relative to the allowed root; or the outside sentinel content is never returned / never opened |
| Command / argument injection | a sentinel file the payload would create does not exist; or the executed argv contains the payload as one argument |
| SQL injection | the query returned only the rows the benign filter admits; or the parameter stayed data (count of rows, not count of tables) |
| SSRF / open redirect | the resolved host or location stays within the allowed set |
| Deserialization / code injection | a sentinel side effect (file, env var, global) was not produced |
| Missing authorization | the protected operation returns the denied result for the unprivileged principal |

Make the sentinel yours: create it in the fixture, check it after the call. Return the invariant from the observation.
Repository-local script, CLI and Java main entry points require native child target-line coverage; a child exit
status or output alone cannot satisfy the coverage gate. Read the runtime guidance before selecting that seam.

## Hypothesis

`target_file` is relative to the repository root. `target_lines` are the lines where the flaw lives (the sink call
and the missing or wrong check), 1-based, as in the file you read with `bash`. `expected_violation` says what the
invariant observes on exploit, in one sentence.

## Build script

Bash, run once in a clean container from the repository root with network, before the network is removed. Follow
the selected runtime skill and `build-recipes`; leave it empty for a plain module tree. Never fetch or run code the
probe does not need.
