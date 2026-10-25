# Agent safety boundaries

Read the [architecture overview](../architecture/overview.md), the repository [security policy](../../SECURITY.md), and the packaged [pilot risk assessment](../../src/corsair/policies/risk.md) before changing an agent boundary. Corsair is a personal-use Python secret-disclosure pilot, not a production security-testing service or a general vulnerability scanner.

## Exactly two bounded roles

The agent layer has exactly two native validation roles:

1. **Producer:** reads an admitted snapshot through `read_file` and `list_files`, then proposes data-only control and adversarial payload values in `Submission`.
2. **Auditor:** has no tools and independently reviews the complete proposal in an outcome-blind `AuditResult`.

Neither role executes source, writes an assertion, creates a probe, changes the operator-owned recipe, observes a private fixture, approves a result, or closes a finding. Do not add arbitrary extra agent security tests, hidden reviewers, or model-authored execution paths to make a narrow case pass. The trusted verifier—not either role—performs the configured native issue-validation work: the benign control and the security safety regression under the admitted recipe.

## Trusted boundaries

- **Local immutable inputs:** source admission and snapshot binding occur before the producer episode. The agent can read only the admitted snapshot; no remote SCM, forge checkout, or arbitrary host path is implemented.
- **Data-only proposals:** the producer chooses payload values, not code, fixed arguments, source paths, fixtures, Docker settings, or exception policy. A valid Pydantic object is not proof of semantic correctness or a vulnerability.
- **Outcome blindness:** execution outcomes, verifier manifests, private values, and oracle labels are excluded from both role packets. The auditor cannot turn a claimed outcome into evidence.
- **Trusted execution and evidence:** Docker SDK sandbox execution, immutable operation intents/receipts, artifact storage, evidence verification, and pure disposition policy live outside the agent tool surface. Unknown or unconfirmed execution is not silently retried into a pass.
- **Credentials:** provider credentials remain in the worker environment. They do not belong in settings examples, source snapshots, workflow arguments, prompts, artifacts, or target containers. Do not add a credential broker, endpoint example, or secret-bearing diagnostic to document an agent.

The implementation does not provide Bedrock or remote-SCM adapters, a general HTTP API, a production MCP/skill loader, or a generic tool catalog. The typed Python workflow API is not an HTTP service. Docker sandbox access and external oracles are trusted components, never agent tools.

## Preserve the security envelope

The native runner applies ADK callbacks and configured call, tool, output, and time budgets. Model-capability-dependent ADK schema handling remains subject to those limits. Keep direct Pydantic `output_schema` validation and the exact round/parent checks; do not reintroduce custom submission repair, automatic replay, fallback agents, or weakened exception handling.

The observer's dedicated-host/container controls do not attest arbitrary malicious target or interpreter behavior. Do not weaken read-only mounts, network isolation, dropped capabilities, no-new-privileges, resource limits, cleanup rules, or source-admission checks to obtain a result. A failed reproduction is `INCONCLUSIVE`, never a negative clearance; a fixed-source result means only that the submitted demonstration was blocked while the benign control remained valid.

The retained **2/3** live composed batch includes a safe-case execution error, not a successful safety finding or a reason to relax policy; see [ISSUE-0010](../plans/active/ISSUE-0010-live-safe-case-probe.md). No production, hostile-target, universal-fix, or population-accuracy claim follows from the current qualification. Security-scope expansion requires a new assessment, conformance evidence, human review of residual risk, and explicit operator authorization. Current plans are indexed in the [plans](../plans/README.md).
