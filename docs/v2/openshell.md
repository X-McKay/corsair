# Corsair v2 OpenShell boundary

`corsair.v2.sandbox.Sandbox` is the **only v2 workload execution path**. It uses the pinned official **OpenShell v0.1.3** tuple:

- Python package: `openshell==0.1.3` from the locked release wheel.
- Lifecycle/inspection/deletion/execution: public `openshell.SandboxClient`.
- Creation and file transfer: official `openshell` v0.1.3 CLI with literal argv, `--from <digest-pinned-image>`, `--policy <operator-policy>`, and `sandbox upload/download`.
- Project-local release package: `/home/ubuntu/corsair-redesign/runtime/openshell/extracted/usr/bin/{openshell,openshell-gateway}`. The downloaded Debian asset is checked against its published SHA-256 before extraction; it is not globally installed.

There is **no Docker/host/SSH/SCP fallback** in the v2 adapter. A missing aligned CLI, an absent/unavailable registered gateway, an uncertain request, or a policy/runtime failure remains a native boundary failure. The gateway is selected through the operator's OpenShell registration, not by accepting an arbitrary direct endpoint URL.

## Profile and registered gateway

The local development profile is operator-owned (`SandboxProfile`) and requires all of:

| Field | Requirement |
| --- | --- |
| `image` | OCI reference pinned by SHA-256 |
| `policy_path` | Absolute, bounded, regular, non-symlink operator policy file |
| `gateway` | Required for sandbox admission: credential-free **native OpenShell gateway registration name** (validated as a bounded name), not an endpoint URL |
| `workspace` | Explicit native workspace, default `default` |
| `workspace_root` | Isolated absolute root, e.g. `/workspace` |

The bundled `src/corsair/v2/data/openshell/development-policy.yaml` and the local Docker development profile are **unqualified**. The policy supplies no provider, host mount, port forward, exposed service, driver configuration, or network policy. It sets Landlock `hard_requirement`; no code downgrades that setting. Validate it against the chosen immutable image on the target host before use. OpenShell registration, native CLI and Python SDK resolve the gateway/auth context from the configured user's `HOME`; a profile's `gateway` is the native registered name. `sandbox.cli_path` can identify a selected CLI binary. A raw endpoint URL (including a hand-supplied TLS URL) is not the Corsair gateway value.

The adapter uses the native registered gateway connection and does **not** pass `--gateway-insecure` or construct a second raw-URL connection path. Keep registration/authentication under the operator's native OpenShell context. Do not place gateway secrets or endpoint credentials in Corsair config.

## Lifecycle and receipts

`acquire(run_id, generation, source_manifest)` creates a deterministic name containing the run/generation and a run hash. Before the native create CLI dispatch, it records a `Store.claim_operation` intent. It applies exact Corsair run/generation/profile/source-manifest/workspace labels, uses the selected image and policy, waits via `SandboxClient.wait_ready`, then fetches a fresh `SandboxRef` and requires its UUID/name/workspace/labels and **actual `Ready` phase** to match.

The lease is bound to `(workspace, name, sandbox UUID)`. The deterministic name or a label alone is never sufficient. An interrupted create response is reconciled only by fetching that exact deterministic name and matching the full claim; no replacement is created under the old claim.

`stage` materializes the immutable `SourceSnapshot` plus bounded pair overlays in a fresh private directory, then uses:

```text
openshell --workspace <workspace> --gateway <registered-gateway-name> \
  sandbox upload <name> <staging-directory> /workspace --no-git-ignore
```

A native `test -d /workspace` SDK command is retained as a bounded staging receipt. It does not make target bytes trusted or prove source immutability after transfer.

`execute` sends one literal argv through `SandboxClient.exec(..., no_login_shell=True, timeout_seconds=...)`. It never retries after dispatch. The v0.1.3 client joins stream output before returning, so Corsair executes the SDK call in a separate worker with a strict address-space cap. Worker death, disconnect, gateway timeout exit `124`, and incomplete terminal delivery are **unknown remote effects**. This is a host-memory containment measure, not an OpenShell runtime-security claim.

Complete bounded stdout/stderr bytes are written to immutable `Store` artifacts (`CommandResult.stdout_ref` / `stderr_ref`). The inline excerpts are at most 16 KiB each so durable Temporal histories do not accumulate megabyte-sized payloads.

`release` first re-checks exact identity. `COMPLETED`/`ALREADY_ABSENT` are confirmed; `ACCEPTED` is followed by UUID-bound `wait_deleted` and a replacement check. A timeout or changed resource is never blindly deleted again. `reconcile` only inspects leases known to the current boundary instance; it never repeats a side effect.

## Bounded native file collection

`read_file` permits only a captured source-manifest path. Native tests use the internal `read_predeclared_report` only for the frozen recipe report path. Both paths:

1. reject lexical escape, source/report allowlist violations, and oversized requests;
2. use SDK `stat` and `sha256sum` to require a remote regular file and hash;
3. invoke the official CLI `sandbox download` to a fresh private destination with host `RLIMIT_FSIZE`;
4. reject local symlinks/special objects/oversize files; and
5. require local bytes and a post-transfer remote stat/hash to match the pre-transfer remote hash.

The source and report are still **untrusted workload claims**. Successful collection is a bounded opaque-byte receipt, not proof that tests executed or semantic assertions are valid.

## NativeTests protocol

`NativeTests.execute` accepts only an `InvestigationPlan(status="planned")` and an exact two-entry pair mapping from the control/security paths to their source bytes. It freezes `digest(pair)`, the source manifest, image/policy identity, sandbox UUID, command receipts, and report artifact reference.

Before native acquisition it rejects a report path colliding with captured source or either probe path. It then performs exactly:

1. native acquisition and stage;
2. every frozen setup argv once;
3. one discovery argv, whose stdout must be exactly two nonempty planned test IDs (no extras);
4. one execution argv;
5. one predeclared report collection and format-keyed admission; and
6. prescribed candidate regression argv once each, if any.

Report admission supports only `junit`, `jest`, `tap`, and `minitest-json`, using the established bounded parsers. There is no language/CWE verdict branch. The report must contain exactly the two selectors and no unexpected result. A security observation gets `failure_type="assertion"` **only** when the admitted native report classifies that test as a failure assertion; setup failures, report errors, native denial, runner crashes, skips, and unknown effects never receive that label.

For a candidate recipe with no `regression_commands`, both passing probes set `regression_passed=True` only as **two scoped correctness checks**; the returned detail explicitly says no broader regression suite was prescribed.

## Qualification posture

The selected local Docker OpenShell profile is intentionally **unqualified**. A running Docker daemon, Docker workload pass, or local gateway health response is not OpenShell qualification. `Sandbox.qualified()` defaults to `False` unless an operator qualification file is supplied and matches the exact observed bindings.

It returns true only for a regular non-symlink **operator attestation** whose declared bindings match all of the following:

- SDK version and local CLI SHA-256;
- profile digest, image digest, and base policy SHA-256;
- observed effective-policy SHA-256; and
- nonempty gateway/supervisor/runtime image/kernel identifiers.

A release string, a loaded YAML file, Docker availability, or an installed gateway is insufficient. The attestation is a local operator-supplied file checked by Corsair; the application does not verify an OpenShell signature or independently certify that the runtime evidence is genuine. It is not a cryptographically signed runtime proof or an automatic certifier. The local Docker profile has no conclusive production qualification here. Any proposed production use requires explicit qualification on the actual target host and profile, with host/runtime/policy facts taken from native observations. Do not provide a fabricated all-true certificate or sample fake digests.

The SDK deletion operation is name-addressed and offers no atomic conditional delete by expected sandbox UUID. The controller therefore needs **exclusive control of the sandbox namespace and names** and uses UUID preflight/postchecks; these checks do not remove a race with another controller. Likewise, gateway-level deletion acknowledgement/absence is not independent evidence of underlying driver garbage collection. Treat ambiguous cleanup as pending/unknown.
