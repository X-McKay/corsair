# Pilot record

What was run, with what, and what happened. Numbers are small-n and come from the operator's local model; they
establish that the mechanics work end to end and give a first gate ledger, not an accuracy claim.

## Environment

| Item | Value |
| --- | --- |
| Branch | `claude/lite`, cut from `develop` at `18f75380` on 2026-10-22 |
| Host | Linux, Docker 29.8.2, Python 3.12, uv 0.11.12 |
| Runtime image | `corsair-lite-python:dev` built from `images/python/Dockerfile` (python:3.12-slim, pytest 9.0.3, coverage 7.13.4) |
| Model | `Qwen3.6-35B-A3B-NVFP4` on the operator's vLLM endpoint; producer profile `local-long` (16384 max tokens, temperature 0, thinking budget 2048), auditor profile `local` (8192) |
| Sandbox | Docker adapter of the `Sandboxes` port: `--cap-drop=ALL`, `--security-opt=no-new-privileges`, cpu/memory/pid limits, network only for the producer's workspace and build replay |

## Offline checks (no model, no containers)

`uv run --locked python -m pytest -q -m "not docker and not live"`: **34 passed**. These exercise the kernel's gates
and verdicts against a scripted sandbox double, the producer loop against a scripted model, the auditor against a
test model, case loading, the matrix and provider profiles.

## Image-only checks (real containers, no model)

`uv run --locked python -m pytest -q -m docker`: **4 passed in 12.4 s**. On the reviewed path-traversal fixture the
reference submission is verified (control holds, exploit violated, both covering line 4 of `documents.py`; on the
fixed tree control holds and exploit holds, so the fix is verified); a benign exploit payload is rejected at
`exploit_run`; an import error is `not_run` at `control_run`; target lines that never execute fail
`control_coverage`; every container is removed.

## Pilot step 1: kernel plus live auditor on the reference submission

`corsair verify --case cases/path-traversal-fixture --submission .../reference-submission.json --provider config/providers.local.json`

Result (run `pilot-verify-1`): **LIKELY_EXPLOITABLE (K1), fix verified**, 21.5 s wall including one auditor call.
All four probe runs covered line 4; outcomes were control `holds` / exploit `violated` on the vulnerable tree and
`holds` / `holds` on the fixed tree, each run 0.7 s. The live auditor accepted the probe, reasoning that it isolates
the target in a temporary directory, applies one assertion to both payloads and checks the hypothesised violation
directly. This is the kernel-only product: a human-written submission verified without a producer.

## Pilot step 2: live producer on the fixture

`corsair investigate --case cases/path-traversal-fixture --provider config/providers.local.json --max-submissions 4`

Result (run `932203ce1856`, before the fix-run feedback described below): **LIKELY_EXPLOITABLE (K1) on the first
submission**, 9 model requests, 27,722 input and 3,082 output tokens, 8 tool calls (5 `bash`, 1 `read_skill`,
1 `submit`), 51 s wall. The producer read the skill, inspected `documents.py`, wrote a probe whose invariant checks
that returned content comes from inside the root, and the live auditor accepted it. On the vulnerable tree the
control held and the exploit violated the invariant, both covering line 4.

The fix came back **not verified**: on the fixed tree the exploit run `errored` with the confinement `ValueError`
that the fix raises, because the producer's probe did not catch it (the reference submission does). The kernel was
right not to call that verified, but the producer never learned why. That motivated one bounded addition: when the
vulnerable gates pass and the fixed-revision exploit raises something other than the probe's own assertion, the
kernel returns a `fix_run` gate with the exception type while keeping the label; the producer may correct the probe
within its remaining budget, and the label can never degrade. This is the first gate-ledger-driven improvement of
the pilot and is covered by offline tests.

## Pilot step 3: live producer on local Python corpus cases

PENDING_EVAL

## Reading the results

- The gate ledger counts which gate rejected submissions. It is the per-objective signal: `ast_guard` and
  `build_replay` are producer contract and environment work; `control_*` is seam location and grounding;
  `exploit_*` is hypothesis quality; `blind_audit` is validity.
- A case whose oracle says `LIKELY_NOT_EXPLOITABLE` is handled correctly when the kernel never emits
  `LIKELY_EXPLOITABLE` for it; the pilot reports `INCONCLUSIVE`, which is the honest label this design gives.
- Tokens and requests are per case from the captured model responses. Wall time includes container work.

## Limits

Docker on the host, root inside the container, pytest only, one model, no repeats, no held-out set. Nothing here is
live qualification in the sense of the main branch's runtime matrix.
