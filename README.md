# Corsair lite

Corsair validates a reported security issue against an exact source revision and, when one exists, its fix. This
branch is the minimal redesign: a **deterministic verdict kernel**, one **producer** agent and one **outcome-blind
auditor**, instead of a five-stage agent pipeline.

The producer explores the vulnerable tree in its own sandbox and submits one *differential probe*: a hypothesis
(file, entry point, lines, mechanism), a build script, and a Python, JavaScript, Java or Perl module defining/exporting `CONTROL_PAYLOAD`,
`EXPLOIT_PAYLOAD` and `run_target(payload)`. The kernel then, in containers the producer never touched:

1. binds the hypothesis to the reported file and checks the probe's contract (Python AST; symbol preflight plus
   native parsing, compilation and export validation for JavaScript, Java and Perl);
2. replays the build script in a clean container with network, removes the network, seals the image;
3. runs `run_target(CONTROL_PAYLOAD)` alone as a native test under coverage: it must return Boolean `true` and execute every
   declared target line;
4. runs `run_target(EXPLOIT_PAYLOAD)` alone through the same setup, target call and invariant: Boolean `false`
   means the reported condition occurred; Boolean `true` means the invariant remained preserved;
5. asks the auditor, which sees only the hypothesis and probe, whether the probe is a fair test;
6. checks the fixed revision independently with the identical probe and exact target-line coverage requirements.

Submissions require `"contract_version": "corsair-lite/differential-probe/2"`. Missing or stale versions are rejected
before sandbox creation. Rewrite old probes to return a Boolean; the kernel never infers or translates old polarity.
The probe receives only the payload, never its role or expected answer. Exceptions and invalid returns are errors.

The trusted driver assigns role-relative results:

| Control result | Exploit result | Audited source disposition |
| --- | --- | --- |
| `PASS` (true) | `PASS` (false) | `LIKELY_EXPLOITABLE` |
| `PASS` (true) | `FAIL` (clean true) | `LIKELY_NOT_EXPLOITABLE`, scoped to this finding, payload, exact revision and runtime; no claim about other attacks |
| Any other combination | | `INCONCLUSIVE`; errors, missing evidence and failed prerequisites cannot establish a negative |

Both decisive labels require accepted blind audit and exact target-line coverage from both runs. Individual results
are `PASS`, `FAIL`, `ERROR`, `NOT_RUN` or `INFRA`; they describe the role observation, not a repository-wide verdict.
Rejected gates return their reason to the producer, which may resubmit within an operator-owned budget. A decisive
source result stops submission, except that a positive source result may retry a correctable fixed-side probe error.
That retry preserves the established positive source label.
Pre-execution build, infrastructure or unsupported-runtime failures may stop as `UNABLE_TO_RUN` or `ERROR`.

The top-level label describes the source revision; each revision also retains its own disposition. A fixed control
`PASS` and exploit `FAIL` verify the fix when the same decisive prerequisites pass. A removed fixed target file yields
`INCONCLUSIVE` with `TARGET_REMOVED` and `fix=not_verified`; no fixed revision yields `not_applicable`.
One driver with two payloads makes "both probes exercise the same real seam" true by construction, and the kernel
still produces two native test ids (`test_probe[control]`, `test_probe[exploit]`), a JUnit report and a coverage
report per run.

## Commands

Requirements: Linux, Python 3.12, `uv`, Docker.

```shell
make sync            # install
make test-offline    # scripted model and sandbox doubles; no Docker, no model
make test            # plus real Python, JavaScript, Java and Perl containers
make verify          # kernel mechanics; no audit configured, so nondecisive
make verify-scripts  # deterministic native script/CLI/main mechanics for all four runtimes; no model
make verify AUDIT_PROVIDER=config/providers.local.json # enable the blind auditor
make verify CASE=cases/path-traversal-javascript
make investigate CASE=cases/path-traversal-fixture PROVIDER=config/providers.local.json
make eval            # reviewed release case for every supported runtime
make historical-eval # unqualified legacy corpus; exploratory, not a release gate
make cleanup         # remove every container this tool created
```

`verify-scripts` replays the four reviewed reference submissions with a test-only accepting auditor. It proves
native execution, exact child coverage, polarity and cleanup without model calls; it does not measure live producer
or auditor quality. Public `make verify` intentionally remains nondecisive unless an auditor provider is configured.

Every run writes `.runs/lite/<run id>/run.json` with each submission's gate, the probe runs (role results, Boolean invariants, exception
types, covered lines, JUnit, coverage and log references), the verdict and the producer's usage. Records include the
resolved runtime image ID and hashes of implementation, prompts, skills and packaged contracts. `oracle.json` files beside
cases are evaluator-only and never reach the agents.

`eval` exits unsuccessfully on any wrong expected label, wrong expected fix, forbidden label or unscored case.
`verify` and `investigate` exit zero for either decisive source disposition and nonzero for a nondecisive result.
Invalid submission JSON or a stale contract version exits with code 2 before creating a sandbox.
The JSON report separates label and fix correctness and includes the gate ledger and runtime for each case.
Use `EVAL_CASES`, `MAX_SUBMISSIONS`, and `REQUEST_LIMIT` to select and bound model work. The default model release
set is the four reviewed direct-call fixtures. Four additional script conformance fixtures are exercised by
`verify-scripts`. Historical corpus oracles retain their original semantics and need review before becoming
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
cases/           reviewed direct and script conformance fixtures per supported runtime, with reference submissions
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
selection follows the reported file, so unrelated tooling cannot select the wrong language. Functions, methods,
repository scripts, CLIs and Java `main` entry points use the same Boolean contract. Ordinary waited child processes
inherit adapter-owned instrumentation and must produce verified native coverage of their target lines; compiling a
launcher or observing stdout/exit status alone is insufficient. Each role/revision runs in a fresh container with
offline read-only source and bounded resources. Detached children, cleared instrumentation, unexpected child exits,
timeouts, output overflow and report failures remain nondecisive.
Unknown adapters and languages fail closed. Legacy image/corpus
directories for other languages are retained as historical inputs, not advertised as supported adapters.
Results in `docs/pilot.md` predate the v2 probe contract, are from the operator's local model and are small-n.

The [agent contracts](src/corsair/agent-contracts.yaml) and [readiness review](docs/readiness.md) document the
playbook alignment and remaining production blockers. Kernel-only `verify` records when no blind auditor is configured;
a fixture run without an auditor remains nondecisive. Deterministic checks demonstrate mechanics, not live model
quality or production sandbox assurance.

| Runtime | Direct fixture | Script fixture / invocation | Inherited evidence and conformance limit |
| --- | --- | --- | --- |
| Python | `path-traversal-fixture` | `cs-0001-b`, waited `sys.executable` CLI | coverage.py subprocess/parallel data; effective startup/configuration must remain inherited |
| JavaScript | `path-traversal-javascript` | `cs-0002-b`, waited `execFile` Node CLI | raw V8 reports merged by literal path; CommonJS/ESM only, no transpiler |
| Java | `path-traversal-java` | `cs-0003-b`, waited `ProcessBuilder` main | append-enabled JaCoCo via `JAVA_TOOL_OPTIONS`; normal orderly child shutdown only |
| Perl | `path-traversal-perl` | `cs-0004-b`, waited list-form child | Devel::Cover shards with inherited Perl paths; byte-identical source ambiguity is nondecisive |

Changes to model-facing guidance still require live `make eval` and `make pilot` comparison with the operator's
provider configuration before merge. A green deterministic script gate establishes mechanics only.
