# Corsair lite

Corsair validates a reported security issue against an exact source revision and, when one exists, its fix. This
branch is the minimal redesign: a **deterministic verdict kernel**, one **producer** agent and one **outcome-blind
auditor**, instead of a five-stage agent pipeline.

The producer explores the vulnerable tree in its own sandbox and submits one *differential probe*: a hypothesis
(file, function, lines, mechanism), a build script, and a Python module defining `CONTROL_PAYLOAD`,
`EXPLOIT_PAYLOAD` and `run_target(payload)`. The kernel then, in containers the producer never touched:

1. checks the probe's structure (three symbols, one payload argument, no mocking libraries);
2. replays the build script in a clean container with network, removes the network, seals the image;
3. runs `run_target(CONTROL_PAYLOAD)` alone as a native pytest test under coverage: it must hold and execute the
   hypothesis' target lines;
4. runs `run_target(EXPLOIT_PAYLOAD)` alone: it must fail with the probe's own assertion (the invariant was
   violated, so the reported condition occurred) and also execute the target lines;
5. asks the auditor, which sees only the hypothesis and probe, whether the probe is a fair test;
6. repeats steps 2 to 4 on the fixed revision to decide whether the fix is verified.

Any failed gate goes back to the producer as the reason, and it may resubmit within an operator-owned budget. The
label is `LIKELY_EXPLOITABLE` only when every gate passed; otherwise `INCONCLUSIVE`, `UNABLE_TO_RUN` or `ERROR`.
One driver with two payloads makes "both probes exercise the same real seam" true by construction, and the kernel
still produces two native test ids (`test_probe[control]`, `test_probe[exploit]`), a JUnit report and a coverage
report per run.

## Commands

Requirements: Linux, Python 3.12, `uv`, Docker.

```shell
make sync            # install
make test-offline    # scripted model and sandbox doubles; no Docker, no model
make test            # plus the kernel on real containers (builds images/python)
make verify          # kernel only, on the reviewed fixture with the reference submission
make investigate CASE=cases/path-traversal-fixture PROVIDER=config/providers.local.json
make eval            # the pilot set against their oracles; writes .runs/lite/eval-<stamp>.json
make cleanup         # remove every container this tool created
```

Every run writes `.runs/lite/<run id>/run.json` with each submission's gate, the probe runs (outcomes, exception
types, covered lines, JUnit and log references), the verdict and the producer's usage. `oracle.json` files beside
cases are evaluator-only and never reach the agents.

## Layout

```text
src/corsair/
  case.py        Case, Finding, Revision (tree digest), request loading; oracles kept separate
  matrix.py      matrix.yaml rows: image + framework + detection hints
  providers.py   operator model profiles (OpenAI-compatible endpoints), two agents, no fallback
  sandbox/       the Sandboxes port and its Docker adapter (hardened containers, labels, environments)
  kernel.py      gates, twin runs, verdict
  auditor.py     the blind auditor agent
  producer.py    the producer agent and its three tools
  cli.py         verify / investigate / eval / cleanup
  skills/        operator-owned Markdown the producer may read
images/python/   the pilot runtime image
matrix.yaml      the runtime matrix
cases/           the reviewed fixture case with its reference submission
evals/e2e/python Local Python corpus cases (input.json + evaluator-only oracle.json)
benchmarks/      the fixture trees and the Python corpus they point at
docs/            design.md (why and what), pilot.md (what was run and what happened)
```

## Scope and honesty

The sandbox is Docker on the host (the image-only tier); the production sandbox is OpenShell behind the same port and
is not part of this branch. The pilot image runs as root inside a hardened container. Only pytest is supported;
other languages arrive as matrix rows plus driver templates. `LIKELY_NOT_EXPLOITABLE` is deliberately not emitted: a
probe that fails to demonstrate a condition proves nothing about absence. Results in `docs/pilot.md` are from the
operator's local model and are small-n.
