# Production readiness review

Reviewed 2026-10-23 against the X-McKay agent playbook contract, capability, evaluation and readiness standards.
The scope is the `feature/duo-refactor` redesign with Python/pytest, JavaScript/node:test, Java/javac and Perl/TAP
runtime adapters.

## Recommendation

**No-go for production.** The branch is suitable for an operator-supervised local pilot on reviewed or otherwise
non-sensitive repositories when the operator explicitly trusts the configured model endpoint and build network.
The deterministic kernel and four runtime adapters have credible image-only evidence; the production isolation,
egress, live-model and operational evidence required for unattended use does not exist yet.

The versioned agent contract is [`src/corsair/agent-contracts.yaml`](../src/corsair/agent-contracts.yaml). It names
the owner, purpose, non-goals, human-governed execution class, budgets, typed boundaries, allowlists, failure
behavior, risk scenarios, records, cleanup and rollback. Runtime selection is an operator-owned, packaged matrix;
unknown frameworks and ambiguous language selection fail closed.

The current submission contract is `corsair-lite/differential-probe/2`: a required explicit version and one
payload-only Boolean invariant, used unchanged across Python, JavaScript, Java and Perl. Missing or stale versions
are rejected before sandbox construction. Control `PASS` means true; exploit `PASS` means false; exploit `FAIL`
means clean true. `LIKELY_NOT_EXPLOITABLE` is scoped to the reported finding, submitted payload, exact revision and
runtime, and makes no claim about other attacks. Both decisive source labels require accepted blind audit and exact
target-line coverage in both roles. Exceptions, invalid returns, absent coverage and infrastructure errors remain
nondecisive. Scripts, CLIs and Java main entry points require verified native child target coverage.

Each revision retains its disposition. Fixed control `PASS` plus exploit `FAIL`, with decisive prerequisites,
verifies the fix; target-file removal is `INCONCLUSIVE/TARGET_REMOVED` and leaves the fix `not_verified`. A source
disposition remains observable independently of fix status. `verify` and `investigate` exit zero only for decisive
source labels; kernel-only verification without a configured auditor remains nondecisive.

## Findings

### P1 — Docker is an image-only test boundary, not production isolation

- **Evidence:** [`src/corsair/sandbox/docker.py`](../src/corsair/sandbox/docker.py) applies CPU, memory and PID limits,
  drops capabilities, disables privilege escalation and removes probe networking. Native tests verify unprivileged,
  read-only source execution and confirmed cleanup. No OpenShell or equivalently qualified production backend was
  exercised on this branch.
- **Observed behavior:** untrusted repository code, dependency installers and model-written code still execute on a
  host Docker daemon. The repository explicitly classifies this as a pilot tier.
- **Impact:** a container or daemon escape could affect the operator host, so high-risk production execution is not
  justified.
- **Remediation and verification:** implement the existing `Sandboxes` port on the production isolation service;
  run escape, network-denial, filesystem, timeout, cancellation, held-identity and cleanup suites on the final
  deployment; obtain the security owner’s acceptance of residual risk.

### P1 — Source disclosure is not bounded by policy-enforced egress

- **Evidence:** producer prompts and shell output are sent to the configured model endpoint. Producer workspaces and
  submitted build scripts use Docker bridge networking so dependencies can be resolved. Probe containers are
  offline, but Docker does not constrain build destinations to approved registries.
- **Observed behavior:** model and build egress are explicit in the contract, but there is no destination allowlist,
  redaction layer, tenant policy or per-run approval artifact.
- **Impact:** confidential source or findings could be disclosed to the model provider or an arbitrary build
  destination.
- **Remediation and verification:** add operator policy for provider/data classification, restricted build egress,
  secret isolation and transcript redaction; add deterministic denial cases for unapproved destinations and
  cross-tenant access.

### P1 — Changed agent behavior lacks current live-model evidence

- **Evidence:** deterministic tests cover budgets, versioned submissions and pre-sandbox stale-version rejection,
  typed output, denied skills, gate
  feedback and four reviewed runtime fixtures. Historical live results in [`docs/pilot.md`](pilot.md) predate the
  four-runtime prompts, Java/Perl capabilities and Boolean v2 probe contract. A current live eval was not completed.
- **Observed behavior:** the release evaluator now requires exact label and fix agreement for every reviewed case,
  rejects forbidden labels and records model, provider, prompt, skill, policy, runtime and oracle hashes. It has no
  current multi-run measurements for task quality, latency, token use or cost.
- **Impact:** producer and blind-auditor quality on the changed contract is unknown, especially for Java and Perl.
- **Remediation and verification:** run the four reviewed cases repeatedly with fixed sampling settings; report pass
  rate, failure gates, p50/p95 latency, tokens, tool calls and cost; review auditor errors and promote failures to
  versioned regression cases. Do not promote the historical corpus until its oracles use lite verdict semantics.

### P2 — Evidence writers share a process with submitted probes

- **Evidence:** drivers capture result paths, roles and serialization functions before importing a probe, and strict
  records are cross-checked with one named, non-skipped test plus coverage. Tampering regressions cover environment
  and serializer mutation. The probe and driver still share their language process.
- **Observed behavior:** a deliberately hostile probe may retain runtime-specific ways to interfere with reporters
  or schedule a late write. This is harder after the trusted-binding changes but not an isolation boundary.
- **Impact:** adversarial model output could attempt to forge or suppress evidence; malformed evidence fails closed,
  but exhaustive non-interference is not established.
- **Remediation and verification:** move final evidence ownership to a supervising process or write-once channel;
  add adversarial late-write, module mutation and process-exit cases for every adapter.

### P2 — Service operations and recovery are intentionally absent

- **Evidence:** runs are human-governed local commands with per-request and per-tool limits, content-addressed
  artifacts, run correlation, explicit cleanup and rollback. There is no durable workflow, SLO, dashboard, alert,
  cancellation recovery or worker-loss replay.
- **Impact:** unattended or service deployment would lack reliable recovery and operational ownership signals.
- **Remediation and verification:** define the service SLO and privacy retention policy, add aggregate budget alerts
  and a runbook, then test cancellation, process loss, duplicate delivery and replay before changing execution class.

## Evidence and scorecard

| Gate | Current evidence | Status |
| --- | --- | --- |
| Contract and construction | Strict Pydantic boundaries; required Boolean v2 submission version; stale-version rejection before sandbox construction; packaged contract/matrix/skills; factory allowlists compared with the manifest | Pass |
| Deterministic contract/capability evals | `make test-offline`, including denied tools, budgets, malformed evidence, symlink escape and eval-gate regressions | Pass |
| Four runtime mechanics | Reviewed vulnerable/fixed fixtures; fresh offline control/exploit containers; coverage.py, V8, JaCoCo and Devel::Cover | Pass |
| Negative native behavior | Import/compile failures, application assertions, hidden JavaScript stacks, missing invariants, bracketed paths, ambiguous Java source identities and driver-binding tampering fail closed | Pass |
| Resource bounds | Container CPU/memory/PID limits plus a streaming 32 MiB combined stdout/stderr cap on every model, build and probe command | Pass |
| Packaging and working-directory independence | Built wheel loads four rows/adapters from `/tmp` and contains the manifest plus six portable runtime/build skills | Pass |
| Live producer and auditor release eval | Exact label/fix gate exists; current four-runtime multi-run report absent | Fail |
| Production isolation and egress | Docker image-only evidence; no qualified backend or destination policy | Fail |
| SLO and operations | Local run records and cleanup exist; no service SLO, dashboard or recovery | Fail |

Risk scenario mapping:

| Scenario | Control/eval evidence | Release decision |
| --- | --- | --- |
| R1 container escape or host impact | Resource/network/filesystem tests on Docker only | Block production pending qualified backend |
| R2 source disclosure through model or build egress | Endpoint is explicit and HTTPS; no policy-enforced destination denial | Block sensitive or unattended use |
| R3 false positive from malformed or spoofed evidence | Shared strict schema, JUnit agreement, exact coverage, exit-code agreement and adversarial regressions | Deterministic gate passes |
| R4 resource exhaustion | Container limits and streaming 32 MiB output cap; overflow becomes an infrastructure result and triggers cleanup | Deterministic control passes |

## Accepted pilot risks and required actions

The repository operator owns all pilot risks. There is no blanket acceptance for production and no calendar
deadline; every P1 must close before a production review. Each pilot invocation is the operator’s authorization for
the named case, configured provider, dependency downloads, local containers and private records. Raw `.runs`,
credentials and private logs must remain uncommitted.

Before another readiness review:

1. qualify the production sandbox and restricted egress policy;
2. strengthen evidence-writer separation;
3. run repeated four-runtime live evals and publish quality, latency and cost distributions;
4. define retention, redaction, SLOs, monitoring and incident runbooks;
5. rerun every deterministic and native hard gate on the final source and record the immutable release revision.

The pre-v2 deterministic snapshot passed 80 offline and 102 complete-suite tests and used four reviewed reference
submissions. Those historical kernel-only labels predate the mandatory accepted-audit gate and are not current
contract evidence. The current deterministic suites cover Boolean role results, source/fixed dispositions,
exception polarity, strict native reports, target coverage and stale-version rejection across all four runtimes.
Passing deterministic checks proves mechanics and policy, while current live-model and production-isolation evidence
remains required.
