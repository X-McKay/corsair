# Corsair lite: development rules

Shared by Codex and Claude Code. Follow the user's scope and authorization; these rules add no approval gate. The
design is in [README.md](README.md) and [docs/design.md](docs/design.md); the pilot record is [docs/pilot.md](docs/pilot.md).

## What the kernel guarantees, and what code may never weaken

- A verdict comes only from `corsair.kernel`: deterministic gates over one probe with two payloads, run as two native
  test ids in the selected runtime, in fresh offline containers built by replaying the submitted build script. No model output is a
  verdict; the blind auditor sees hypothesis and probe, never an outcome, and can only reject.
- Submissions require `contract_version="corsair-lite/differential-probe/2"`; reject stale/missing versions before
  sandbox creation. One payload-only Boolean invariant uses the same setup, target call and check for both roles;
  it receives no role or expected answer. True means preserved and false means the reported condition occurred.
  Control `PASS` means true; exploit `PASS` means false; exploit `FAIL` means clean true.
- `LIKELY_EXPLOITABLE` requires both roles `PASS`. `LIKELY_NOT_EXPLOITABLE` requires control `PASS` and exploit
  `FAIL`, and is scoped to the finding, payload, exact revision and runtime; it says nothing about other attacks.
  Both decisive labels require accepted blind audit and exact target-line coverage from both runs. Exceptions,
  invalid returns, missing reports, uncovered targets and infrastructure failures cannot establish a negative.
- Each revision retains its own disposition; the top-level label describes the source revision. Fix `verified`
  requires fixed control `PASS`, exploit `FAIL`, and the same decisive prerequisites. A removed fixed target file is
  `INCONCLUSIVE/TARGET_REMOVED` with `not_verified`; no fixed revision is `not_applicable`.
- Functions, methods, scripts, CLIs and Java main entry points use the same contract. Child-process execution
  requires verified native target coverage; stdout or exit status alone cannot ground a disposition.
- The producer stops on either decisive source label. Only a positive source with a correctable fixed-side probe
  error may retry, preserving its source label. `verify` and `investigate` exit zero only for a decisive source label;
  `INCONCLUSIVE`, `UNABLE_TO_RUN` and `ERROR` are nondecisive stops. Invalid submissions exit 2 before any sandbox.
- The producer's workspace is never evidence. Everything it did is replayed from the submission in containers it
  never touched. Model-written code never runs on the host.
- Labels and oracles (`oracle.json`) are evaluator-only and never reach a `Case`, a prompt or a tool result.
- Containers: all capabilities dropped, no new privileges, no network except during build replay and in the
  producer's working sandbox, resource limits, deterministic names and labels, cleanup confirmed against identity.
  A held identity is never reused or removed by the attempt that found it.

## How to change it

- Keep it small. Every module has one job: `case`, `matrix`, `providers`, `sandbox`, `kernel`, `auditor`,
  `producer`, `cli`. Add a module only to remove a responsibility from another. Languages are matrix rows and images,
  not code paths, once the kernel supports their framework.
- Skills in `src/corsair/skills/` are operator-owned guidance. A skill or prompt change is an agent behaviour change:
  rerun `make eval` and compare the gate ledger and verdict accuracy before merging.
- Checks: `make test-offline` for any change (scripted model and sandbox doubles); `make test` when the kernel,
  sandbox or image changed (real containers); `make pilot` with the operator's provider config for agent changes.
  Report each check as passed, failed, blocked or unrun. A passing double proves mechanics, never model quality.
- Prefer PydanticAI, pytest, coverage.py and the Docker CLI as they are. Do not add a scheduler, graph engine, retry
  framework, tracing system or a second sandbox abstraction. Record the upstream gap before any bespoke code.
- Never commit `.runs/`, `.venv/`, credentials or raw private logs. Commit, push and publish only within the user's
  authorization.
