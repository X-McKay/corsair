# Corsair lite

Corsair validates a reported security issue against an exact source revision and, when one exists, its fix. This
branch is the minimal redesign: a **deterministic verdict kernel**, one **producer** agent and one **outcome-blind
auditor**, instead of a five-stage agent pipeline.

The producer explores the vulnerable tree in its own sandbox and submits one *differential probe*: a hypothesis
(file, function, lines, mechanism), a build script, and a Python, JavaScript, Java or Perl module defining/exporting `CONTROL_PAYLOAD`,
`EXPLOIT_PAYLOAD` and `run_target(payload)`. The kernel then, in containers the producer never touched:

1. binds the hypothesis to the reported file and checks the probe's contract (Python AST; symbol preflight plus
   native parsing, compilation and export validation for JavaScript, Java and Perl);
2. replays the build script in a clean container with network, removes the network, seals the image;
3. runs `run_target(CONTROL_PAYLOAD)` alone as a native test under coverage: it must hold and execute every
   declared target line;
4. runs `run_target(EXPLOIT_PAYLOAD)` alone: its invariant must be violated (Python raises its own assertion;
   JavaScript, Java and Perl return false for a kernel-owned assertion), and it must also execute the target lines;
5. asks the auditor, which sees only the hypothesis and probe, whether the probe is a fair test;
6. checks the fixed revision: both payloads must hold and execute the target file. Missing coverage cannot verify a fix.

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
make test            # plus real Python, JavaScript, Java and Perl containers
make verify          # kernel only, on the reviewed fixture with the reference submission
make verify CASE=cases/path-traversal-javascript
make investigate CASE=cases/path-traversal-fixture PROVIDER=config/providers.local.json
make eval            # reviewed release case for every supported runtime
make historical-eval # unqualified legacy corpus; exploratory, not a release gate
make cleanup         # remove every container this tool created
```

Every run writes `.runs/lite/<run id>/run.json` with each submission's gate, the probe runs (outcomes, exception
types, covered lines, JUnit, coverage and log references), the verdict and the producer's usage. Records include the
resolved runtime image ID and hashes of implementation, prompts, skills and packaged contracts. `oracle.json` files beside
cases are evaluator-only and never reach the agents.

`eval` exits unsuccessfully on any wrong expected label, wrong expected fix, forbidden label or unscored case.
The JSON report separates label and fix correctness and includes the gate ledger and runtime for each case.
Use `EVAL_CASES`, `MAX_SUBMISSIONS`, and `REQUEST_LIMIT` to select and bound model work. The default release set is
the four reviewed fixtures. Historical corpus oracles retain their original semantics and need review before becoming
release baselines for this redesign; `make historical-eval` keeps them explicit and never silently relabels them.

For builds behind a TLS proxy, supply its public CA through `DOCKER_BUILD_FLAGS="--secret id=proxy_ca,src=/path/to/ca-bundle.pem"`.

## Layout

```text
src/corsair/
  case.py        Case, Finding, Revision (tree digest), request loading; oracles kept separate
  matrix.py      matrix.yaml rows: image + framework + detection hints
  matrix.yaml    packaged runtime matrix; root matrix.yaml links here
  agent-contracts.yaml  purpose, typed boundaries, capability allowlists, budgets and risk classification
  providers.py   operator model profiles (OpenAI-compatible endpoints), two agents, no fallback
  sandbox/       the Sandboxes port and its Docker adapter (hardened containers, labels, environments)
  kernel.py      gates, twin runs, verdict
  frameworks/    pytest, node:test, javac/JaCoCo and Perl/TAP adapters; shared evidence validation
  auditor.py     the blind auditor agent
  producer.py    the producer agent and its three tools
  cli.py         verify / investigate / eval / cleanup
  skills/        allowlisted, portable <name>/SKILL.md runtime guidance
images/python/   Python/pytest pilot image
images/javascript/  Node 22/node:test pilot image
images/java21/   Java 21/JaCoCo pilot image
images/perl/     Perl 5.40/Devel::Cover pilot image
cases/           reviewed fixture per supported runtime, with reference submissions
evals/e2e/python Local Python corpus cases (input.json + evaluator-only oracle.json)
benchmarks/      the fixture trees and the Python corpus they point at
docs/            design.md, historical pilot.md, current readiness.md
```

## Scope and honesty

The sandbox is Docker on the host (the image-only tier); the production sandbox is OpenShell behind the same port and
is not part of this branch. Builds use the image's user; probes run unprivileged as 1000:1000 against readable,
read-only source, with capabilities dropped and no network. Python/pytest, JavaScript/node:test, Java 21 with
javac/JaCoCo, and Perl 5.40 with TAP/Devel::Cover are supported. JavaScript targets may use CommonJS or ESM; Java
builds normalize compiled classes into one documented directory; Perl modules load through `PERL5LIB`. Runtime
selection follows the reported file, so unrelated tooling cannot select the wrong language. Unknown adapters and languages fail closed. Legacy image/corpus
directories for other languages are retained as historical inputs, not advertised as supported adapters.
`LIKELY_NOT_EXPLOITABLE` is deliberately not emitted: a
probe that fails to demonstrate a condition proves nothing about absence. Results in `docs/pilot.md` are from the
operator's local model and are small-n.

The [agent contracts](src/corsair/agent-contracts.yaml) and [readiness review](docs/readiness.md) document the
playbook alignment and remaining production blockers. Kernel-only `verify` records when no blind auditor is configured;
a passing fixture run demonstrates mechanics, not live model quality or production sandbox assurance.
