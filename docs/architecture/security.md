# Security architecture

Corsair's security design limits what agents can do, binds evidence to admitted inputs, confines native target execution, and keeps the verdict in deterministic code. It is a personal-use pilot, not a production-qualified hostile-code analysis platform. The authoritative risk statement is the packaged [pilot risk assessment](../../src/corsair/policies/risk.md); this page summarizes its architectural controls and links the operating policies that govern them.

## Security authorities

- Read the root [security policy](../../SECURITY.md) for reporting and project-wide security process.
- Read [agent safety](../agents/safety.md) for role and prompt-facing safety constraints.
- Read [disaster recovery](../operations/disaster-recovery.md) for restoration, uncertainty, and retained-artifact procedures.
- Read the packaged [risk assessment](../../src/corsair/policies/risk.md) before admitting source or extending the pilot.

## Non-negotiables

1. The label is decided by code in [`policies/verdicts.py`](../../src/corsair/policies/verdicts.py). Neither agent can assign, raise, or confirm a label.
2. The auditor never sees an outcome. Its packet contains the finding, public recipe configuration, source excerpt, and proposed pair; it has no tools and can only reject.
3. The producer proposes JSON payload data only. It never authors a probe or any executable code; the kernel owns the recipe and materializes it at run time ([ADR 0004](decisions/0004-payload-pair-and-coverage-gated-verdict.md)).
4. Control and exploit come from one differential run pair that differs only in payload.
5. Exact target-line coverage is required in both runs before an observation counts toward any label.
6. `EXPLOIT_NOT_DEMONSTRATED` needs at least two independent producer sessions (`negative_threshold = 2`).
7. `EXPLOIT_DEMONSTRATED` rests on the vulnerable-revision differential; a supplied fix revision is optional confirmation and only withholds the label when the exploit still demonstrates on it.

## Trust boundaries and controls

| Boundary | Control | Limit |
| --- | --- | --- |
| Source admission | Operator-scoped local root; descriptor/no-follow traversal; regular-file, size, count, sensitive-name, and digest checks; deterministic immutable archive | Not remote-SCM trust, malware scanning, or a general secret detector. |
| Pre-model gates | `target_binding`, `ast_guard`, and `build_replay` run before any model call; a case that cannot be exercised is `UNABLE_TO_RUN` | These gates prove reachability of the recipe, not absence of other weaknesses. |
| Producer episode | Canonical structured output; bounded model/tool/time budgets; read-only `read_file`/`list_files` and the skills toolset over an immutable snapshot; data-only payload pair | A valid pair can still be the wrong pair; model roles can share correlated failure. |
| Auditor episode | No tools; outcome-blind packet; structured reject-only output | A non-rejection is not an endorsement and never raises a label. |
| Probe authoring | The kernel writes the probe from the operator-owned recipe and the proposed payloads; agents cannot alter the recipe, fixed arguments, or assertions | The recipe set is the pilot's scope; it does not generalize to arbitrary findings. |
| Container execution | Docker SDK, unprivileged user, dropped capabilities, no-new-privileges, read-only mounts, no network, resource/output/time limits, and cleanup confirmation | Docker daemon/kernel compromise and hostile interpreter evasion remain outside the containment claim. |
| Coverage gate | Exact target-line coverage required in both control and exploit runs; an uncovered run is discarded as `INCONCLUSIVE` | Coverage shows the line ran, not that the payload was the strongest possible one. |
| Evidence acceptance | Immutable raw receipts; operation/source/submission/image identity; native exit/test report/driver/coverage agreement; trusted verifier | A receipt supports only the defined recipe and scoped component claim. |
| Negative labels | Independent-session threshold; fixed differential for positives; `INCONCLUSIVE`/`UNABLE_TO_RUN`/`ERROR` are never clearance | Two agreeing sessions reduce, but do not remove, correlated producer error. |
| Durable side effects | Immutable pre-execution intent, committed observations, identity reconciliation, no automatic replay of unknown execution | An interrupted operation can remain uncertain; uncertainty is not a pass. |
| Credentials and diagnostics | Worker environment holds provider credentials; settings reject URL credentials; logs are sanitized metadata | Operational metadata still warrants restricted handling. |

## Scoped conclusions

Only the kernel assigns labels, and only after every earlier gate passed. `EXPLOIT_DEMONSTRATED` means the proposed exploit payload demonstrated the reported condition at the covered target line while the benign control held and the auditor did not reject the pair, and the demonstration covers the finding's claimed scope. A fix revision is not required; when one is supplied, the label is confirmed if the same pair no longer demonstrates on it and withheld if it still does. `COMPONENT_EXPLOIT_DEMONSTRATED` is that same genuine differential when the finding claimed application scope but only the component seam was exercised, so reachability to the claimed application entry point was not established; it is a scoped positive, never a soft landing for a weak demonstration. `EXPLOIT_NOT_DEMONSTRATED` means at least two independent, coverage-valid, non-rejected sessions failed to demonstrate it. Everything else is `INCONCLUSIVE`, `UNABLE_TO_RUN`, or `ERROR`; none of those is proof that a target is safe.

The costliest error is a false `EXPLOIT_NOT_DEMONSTRATED`. The gate order exists to make that label the hardest to reach: a case that cannot run, a run that missed the target line, a rejected pair, or a single session all stop short of it. A fixed-revision observation is similarly narrow: the submitted demonstration was blocked while the benign control held. It is not universal patch correctness. The architecture makes no production, hostile-target, or population-accuracy claim, no clearance claim, and no claim that local artifacts survive host loss.

## Operational posture

Use a dedicated disposable host without production workloads or unrelated credentials. Do not mount the Docker socket or workload credentials into target containers, enable target networking, weaken resource limits, bypass TLS, or substitute an unreviewed image to obtain a run. The pilot admits only local source snapshots and runs only the Docker sandbox adapter; the OpenShell adapter is deferred. Live runs with a Docker daemon, a Temporal service, and a model endpoint happen on a separate rig; the cloud development environment cannot run them. Any new source provider, language runtime, recipe, sandbox adapter, privileged capability, remote publication path, or deployment tier requires a new risk assessment and qualification rather than a documentation-only extension.

See [System context](system-context.md) for information boundaries, [Data flow](data-flow.md) for the gate order and reconciliation path, and [Deployment architecture](deployment.md) for persistence dependencies.
