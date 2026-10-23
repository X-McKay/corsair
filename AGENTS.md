# Corsair lite: development rules

Shared by Codex and Claude Code. Follow the user's scope and authorization; these rules add no approval gate. The
design is in [README.md](README.md) and [docs/design.md](docs/design.md); the pilot record is [docs/pilot.md](docs/pilot.md).

## What the kernel guarantees, and what code may never weaken

- A verdict comes only from `corsair.kernel`: deterministic gates over one probe with two payloads, run as two native
  pytest test ids in fresh offline containers built by replaying the submitted build script. No model output is a
  verdict; the blind auditor sees hypothesis and probe, never an outcome, and can only reject.
- Polarity: `holds` means the probe's invariant held; `violated` means the probe's own assertion failed, i.e. the
  reported condition occurred. `LIKELY_EXPLOITABLE` needs control `holds` and exploit `violated` on the vulnerable
  revision with both runs executing the target lines. `LIKELY_NOT_EXPLOITABLE` (K4) needs, over one investigation, at
  least `negative_threshold` distinct submissions (operator-owned, default 2, never agent-editable) that each passed the
  structural guard, the build, control `holds`, exploit `holds` on the vulnerable revision with both runs executing the
  target lines, and the blind audit where configured. Any `LIKELY_EXPLOITABLE` submission wins over negatives. The fix
  is annotation only: it never changes a decisive label, and it is not run for `LIKELY_NOT_EXPLOITABLE`. A fix is
  `verified` only when the fixed revision shows control `holds` and exploit `holds`. `INCONCLUSIVE`, `UNABLE_TO_RUN` and
  `ERROR` are honest stops.
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
