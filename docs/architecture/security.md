# Security architecture

Corsair’s security design limits what agents can do, binds evidence to admitted inputs, and confines native target execution. It is a personal-use pilot, not a production-qualified hostile-code analysis platform. The authoritative risk statement is the packaged [pilot risk assessment](../../src/corsair/policies/risk.md); this page summarizes its architectural controls and links the operating policies that govern them.

## Security authorities

- Read the root [security policy](../../SECURITY.md) for reporting and project-wide security process.
- Read [agent safety](../agents/safety.md) for role and prompt-facing safety constraints.
- Read [disaster recovery](../operations/disaster-recovery.md) for restoration, uncertainty, and retained-artifact procedures.
- Read the packaged [risk assessment](../../src/corsair/policies/risk.md) before admitting source or extending the pilot.

## Trust boundaries and controls

| Boundary | Control | Limit |
| --- | --- | --- |
| Source admission | Operator-scoped local root; descriptor/no-follow traversal; regular-file, size, count, sensitive-name, and digest checks; deterministic immutable archive | This is not remote-SCM trust, malware scanning, or a general secret detector. |
| Agent episode | Canonical structured output; bounded model/tool/time budgets; producer read-only `read_file`/`list_files`; tool-free outcome-blind auditor | A valid model object can still be semantically wrong; model roles can share correlated failure. |
| Source/evidence separation | Private fixture is generated only for the native observer and excluded from agent packets, artifacts’ reasons, and logs | The design does not attest arbitrary target/interpreter behavior. |
| Container execution | Docker SDK, unprivileged user, dropped capabilities, no-new-privileges, read-only mounts, no network, resource/output/time limits, and cleanup confirmation | Docker daemon/kernel compromise and hostile interpreter evasion remain outside the containment claim. |
| Evidence acceptance | Immutable raw receipts; operation/source/submission/image identity; native exit/JUnit/driver/coverage agreement; trusted verifier | A receipt only supports the defined recipe and scoped component claim. |
| Durable side effects | Immutable pre-execution intent, committed observations, identity reconciliation, no automatic replay of unknown execution | An interrupted operation can remain uncertain; uncertainty is not a pass. |
| Credentials and diagnostics | Worker environment holds provider credentials; settings reject URL credentials; logs are sanitized metadata | Operational metadata still warrants restricted handling. |

## Scoped conclusions

Only trusted policy code assigns dispositions after source/evidence checks. `SUPPORTED` means the admitted demonstration occurred within the component scope. `CONDITIONAL` preserves the distinction between component evidence and an application-level claim. A failed reproduction, provider block, source denial, unknown operation, sandbox failure, or execution error is `INCONCLUSIVE` or an operational status, never proof that a target is safe.

A fixed-source observation is similarly narrow: the submitted demonstration was blocked while the benign control held. It is not universal patch correctness. The architecture makes no production/hostile-target/population-accuracy claim, no negative clearance claim, and no claim that existing local artifacts survive host loss.

## Operational posture

Use a dedicated disposable host without production workloads or unrelated credentials. Do not mount the Docker socket or workload credentials into target containers, enable target networking, weaken resource limits, bypass TLS, or substitute an unreviewed image to obtain a run. The current implementation admits only local source snapshots; it has no remote SCM integration. Any new source provider, language, observer recipe, privileged capability, remote publication path, or deployment tier requires a new risk assessment and qualification rather than a documentation-only extension.

See [System context](system-context.md) for information boundaries, [Data flow](data-flow.md) for the identity and reconciliation path, and [Deployment architecture](deployment.md) for persistence dependencies.
