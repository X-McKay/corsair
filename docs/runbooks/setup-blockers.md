# Early stops and setup blockers

A stop means this attempt cannot establish the requested result. It is not evidence that an application issue is absent or fixed. Start with the diagnostic code, its certainty, owner and evidence reference. `Blocker.render()` provides a plain-text view; the typed object is available in `RuntimeOutcome.diagnostic`, `SetupRun.diagnostic` and final `BlockedEnvironment.diagnostics`. The run's command, operation ID, hashes and native stdout/stderr remain in the private setup ledger and execution receipt. Use `read_output(run_id, stream, offset)` for a focused output window; do not publish raw private logs or credential-bearing command URLs.

## Implemented stop points

Runtime admission stops before an environment-agent input is constructed. Setup stops dispatching after infrastructure errors, uncertain delivery/completion, substantive command failures or exhausted budgets. Read-only inspection remains available. A budget-refused call never dispatched and does not invalidate complete successful evidence.

For a narrow invocation error, `SetupRun.correction_available` permits an explicit changed command with `correction={run_id, reason}`: an unrecognized pytest argument under the same executable. Missing Maven remains terminal; do not switch to a repository wrapper that may download an unqualified toolchain. The operator allows at most two corrections (or disables them with `SetupBudget(max_corrections=0)`), still within the total command budget. No failed invocation may be repeated. Unresolved corrections block ready; successful corrections retain failed receipts and still require all normal setup evidence. Inspect output and repository guidance first: a usage error does not prove absence of side effects. Unknown execution, policy, TLS, dependency, build and assertion failures do not get this allowance. Other corrections require a new attributable attempt after the developer/operator resolves the cause; the code never automatically retries, switches images, changes pins, expands network policy or installs credentials.

| Code | What to inspect | Action and owner |
| --- | --- | --- |
| `image_unavailable` | Language, all required component version ranges, `selection.needs`, per-image `selection.rejected`, cited source declarations | Operator adds a matching digest-pinned image, builds and qualifies it, then registers its runtime and framework rows. Follow the [base-image skill](../../.claude/skills/corsair-base-image/SKILL.md). A preferred version is a suggestion, not an admitted image. |
| `framework_unqualified` | Matching runtime and unmet test framework/version | Qualify the runner and parser on that image; register only the exact tested framework versions. A new runtime image may not be needed. |
| `image_not_prepared` | Selected row, node and prepared-image receipt/digest | Operator prepares and loads the existing image on this node using the [toolchain runbook](openshell-toolchains.md). Do not register a duplicate or substitute the upstream base digest. |
| `runtime_undetermined` | Missing/conflicting declarations, unresolved parent manifests, source path/line | Developer supplies metadata, corrects the project root or fixes unsupported parsing before selecting an image. Do not guess a runtime. |
| `dependency_resolution` | Exact package/artifact/version in the cited package-manager error; lockfile, registry and platform | Developer checks availability and conflicting constraints. First inspect preceding network/auth failures: “not found” does not establish a reachable registry. Preserve pins; no automatic version substitution. |
| `registry_access` | Attempted registry URL, response status, supported authentication path | Operator checks access and registry health. HTTP 401/403 alone does not prove OpenShell policy denial. Never place private workload credentials in the sandbox. |
| `tls_trust` | Endpoint, certificate chain, CA/proxy configuration and clock | Operator repairs intended trust configuration. Keep TLS verification enabled. |
| `connectivity` | Exact attempted host/port, DNS, proxy, gateway and destination availability | Investigate from the same execution boundary. Correlate native OpenShell policy evidence before proposing a narrowly scoped policy change. A timeout/refusal does not identify the denying layer. |
| `storage_capacity` | Workspace/node capacity, inodes, quota and retained native error | Operator reclaims only owned resources or reviews the budget; no blind deletion. |
| `setup_command_failed` | The exact failing command and output | Developer distinguishes compilation, test discovery, baseline assertion and other native failures. Generic exit codes are not enough to assert a cause. |
| `execution_not_dispatched` | Native error type/status, host admission, sandbox immutable identity and gateway | Fix the recorded execution-boundary cause before a new attempt. No workload completion is claimed. |
| `execution_unknown` | Operation receipt and original sandbox state | Stop. Reconcile via the supported runtime before resending anything; inspect gateway/transport health. |
| `output_limit` / `setup_budget` | Output volume or command trajectory and configured budget | Reduce unnecessary work; operator reviews any budget increase. An output limit may leave remote execution unknown. |
| `receipt_storage` / `execution_failure` | Journal/artifact permissions/capacity and original native receipt | Restore evidence integrity and reconcile execution. Exit zero cannot override a journal error. |
| `cleanup_unconfirmed` | Original worker/sandbox identity and cleanup evidence | Confirm cleanup through supported operations. Do not report deletion or repeat the workload merely because cleanup was attempted. |

For example, an unsupported Python range is presented as the actual range plus the build-tool and framework requirements and source references, not “Python failed.” A failed package install gets one diagnostic and a run reference identifying its exact attempted command and retained package-manager error. Output matches are explicitly **reported symptoms**; raw output is untrusted and cannot authorize remediation. Unknown or unsupported error formats stay generic with the original evidence intact.

## Brainstorm and next boundaries

These remain follow-up producer integrations, not implemented coverage or live qualification:

| Boundary | Earliest decisive gate | Useful guidance/evidence |
| --- | --- | --- |
| Input/source acquisition | Before fetching or executing repository content | Missing/ambiguous revision, source identity mismatch, unsupported archive/submodule, oversized tree: show exact requested identity and failing admission limit. |
| Host and sandbox admission | Before sandbox creation or model setup | Capacity, kernel/CNI, runtime readiness, policy profile and owned identity: preserve the native admission report and required runbook step. |
| Dependency closure | Before build | Exact unresolved coordinates, checksum mismatch, unavailable wheel/platform, offline cache incompleteness, disallowed custom registry: separate availability, compatibility, integrity and policy evidence. |
| Test discovery | Before authoring or assessing a fix | Zero discovery, wrong selectors, unsupported framework, skipped baseline: show observed IDs/counts and expected test contract; do not interpret these as passing tests. |
| Provider/agent | Before or during native SDK calls | Missing provider configuration, authentication, rate/usage limits, model timeout, invalid output/tool calls: keep native type/status and attempt identity, distinguish input refusal from model failure. |
| Durable execution | At recorded activity outcome | Preserve nonretryable domain stops and unknown delivery; use native Temporal retry policy, not a bespoke retry loop. Replays need separate qualification. |
| Cancellation/cleanup | At cancellation or teardown | Preserve immutable resource identities and confirmed/unconfirmed cleanup, retain earlier blocker as primary evidence. |

Preflight should batch independent read-only checks where safe, but never probe arbitrary hosts, download repository dependencies on the host, or spend provider calls to diagnose a deterministic configuration failure. A resume must revalidate the changed dependency and its consumers, not reuse stale qualification.

The runtime/environment handoff remains unconnected to the full real-case chain under G12. This change improves those existing component entry points only. It does not add a new end-to-end CLI or qualify a live OpenShell/network/provider path. [SPEC-0053](../development/specs/SPEC-0053-actionable-blockers.md) and [PLAN-0057](../development/plans/PLAN-0057-actionable-blockers.md) track implementation and checks.
