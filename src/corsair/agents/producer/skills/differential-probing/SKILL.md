---
name: differential-probing
description: Design fair control and exploit probes for the verification kernel.
---
# Differential probing

One probe module, two payloads, one invariant. The kernel verifies it; you cannot argue with the kernel, only fix
the probe.

## Contract

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
- The exploit run must fail with **your** `assert` (an `AssertionError` raised in the probe). A `TypeError`,
  `FileNotFoundError` or an exception from inside the application is `errored`, not a demonstration. Catch
  expected exceptions from the target when the invariant is about what happens afterwards (for example "the
  outside file was not opened"), and let the invariant decide.
- Both runs must execute every requested target line, not merely one line or a similarly named file.
- Use ordinary inputs of the accepted public type; never tag an input as control/exploit or attach an expected
  outcome to it. Compute the same security invariant from actual target behavior and input properties.
- For foreign languages, call the native target with subprocess argument lists and inherited environment.
  A subprocess setup failure must raise a non-assertion error; a crash is proof only when a specific relevant
  diagnostic is the invariant and native target coverage is present. Do not assert merely on nonzero exits.
- No `unittest.mock`, `pytest_mock`, `responses`, `httpretty`. If a dependency must be controlled, pass a real
  object through the target's own parameters; never replace the function that owns the security property.
- Imports: the repository root is `/work` and on `sys.path`. Import the target the way its own tests do.
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

Bash, run once in a clean container from the repository root with network, before the network is removed. Use
`pip install -e .` or `pip install -r requirements.txt` only when the probe needs the package importable or its
dependencies present. Leave it empty for a plain module tree. Never fetch or run code the probe does not need.
Use the matching runtime-selection and language build guide for Maven, Gradle, Vite, Bundler, CPAN or CMake.
