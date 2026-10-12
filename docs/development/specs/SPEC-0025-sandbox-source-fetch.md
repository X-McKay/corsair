---
id: SPEC-0025
kind: spec
title: In-sandbox pinned source fetch
status: draft
updated: 2026-10-12
related: [IDEA-0004, ISSUE-0006, SPEC-0006, SPEC-0010, SPEC-0011, SPEC-0012, SPEC-0026, PLAN-0021]
---

# In-sandbox pinned source fetch

## Goal and scope

The environment agent and every later execution stage need a real project's complete source tree inside a sandbox. Host-to-sandbox tree transfer is blocked by [ISSUE-0006](../issues/ISSUE-0006-native-transfer-retry-admission.md): pinned OpenShell 0.1.3 retries whole transfers after possible mutation and offers no pre-extraction byte, member or inode bound. The user selected a different route on 2026-10-12: the sandbox fetches the source itself from the hosting service with read-only access, and nothing is pushed back. This spec defines that fetch as the specifically reviewed narrower contract ISSUE-0006 allows. It is a deterministic node, not an agent.

In scope: one GitHub or Azure DevOps repository, public or private, fetched over HTTPS at one exact commit into a fresh sandbox, verified against the host's own immutable capture before any repository code runs. Private-repository access uses an OpenShell provider so the real token never enters the workload (below). Excluded: submodules, Git LFS, dependency or registry access ([SPEC-0026](SPEC-0026-sandbox-dependency-fetch.md)), writes, commits, pushes, and any change to the general transfer criteria of ISSUE-0006.

## Boundaries and design

**Two copies with separate roles.** The host capture from `GitSource` (SPEC-0012) remains the authoritative `SourceSnapshot` with `commit` and `tree`. The sandbox clone is a working copy admitted only when its native commit and tree identities equal that snapshot. Agents keep reading the host capture; the sandbox copy is what the build and tests execute.

**Fetch recipe.** Operator-owned and fixed, run with the admitted toolchain image's pinned `git` before any repository content is executed: initialize an empty directory; `git -c core.hooksPath=/dev/null -c protocol.allow=never -c protocol.https.allow=always -c transfer.fsckObjects=true -c submodule.recurse=false fetch --depth=1 --no-tags <url> <commit>`; check out that commit with LFS smudge and all filters disabled; then print `git rev-parse HEAD HEAD^{tree}` and the tracked file count to stdout. Git clone and fetch do not run repository hooks, and the configuration above also refuses non-HTTPS transports, submodule recursion and filters. GitHub serves reachable commits by SHA. The user directed on 2026-10-12 that Azure DevOps is assumed to do the same; live qualification confirms it, and a refusal there fails as `dependency` layer rather than falling back to a branch fetch.

**Identity admission.** The bounded stdout receipt from the existing execution adapter (SPEC-0010) is compared on the host with the `SourceSnapshot`. Any mismatch, missing field, extra output or nonzero exit refuses the sandbox for execution. The values are produced inside the sandbox, but only the pinned image's `git` has run there by then, so they are as trustworthy as the admitted image. After repository code runs, the working copy is untrusted. Later stages use the existing staging-copy and before/after integrity contract for that.

**Network phases.** The sandbox starts with a policy granting only HTTPS to the single repository host, for the pinned `git` binary. Once identity admission passes, the native `policy set --wait` narrows the sandbox to deny that endpoint. Deny-by-default network was qualified in [SPEC-0006](SPEC-0006-openshell-policy.md), which already exercised narrowing and endpoint removal on a running sandbox, with loaded revisions observed. A new matching denial event must then be observed from inside the sandbox before any repository code runs. Stored but unloaded policy never counts.

**Retries and unknown outcomes.** The sandbox is disposable. A failed, partial or unknown fetch is never repaired in place: the sandbox is deleted with confirmed cleanup and a new one is created. That removes the ISSUE-0006 concern for this path, because there is no host-side extraction and the only bytes entering host storage are the bounded receipt.

**Limits.** Fetch wall time, sandbox storage and memory are operator budgets, enforced by the existing execution and sandbox limits rather than by trusting the repository. A fetch that exceeds them fails as `dependency` or `sandbox` layer with retained native detail, never as an application result.

**Credentials for private repositories.** The user directed on 2026-10-12 that private repositories are allowed and that the Azure DevOps personal access token (`ADO_PAT`) is supplied to OpenShell for its credential proxy, not to the workload. The design depends on OpenShell's provider placeholder mechanism, as described in current secondary documentation: the sandbox environment holds an opaque placeholder, and the proxy outside the workload substitutes the real value only on outbound requests to the provider's bound host, port and path, including basic-auth values; unknown, malformed or expired placeholders fail closed, and traffic the proxy does not inspect gets no credential. Under that model:

- The operator registers one provider holding the token and attaches it at sandbox creation (providers cannot be added to a running sandbox). The token's binding is the single repository host. Git uses the placeholder as the basic-auth password; Azure DevOps accepts a PAT that way.
- The token never appears in the workload's environment, files, receipts, evidence or Git. Receipts and logs are checked for the token value and refused if it appears.
- Any process the network policy lets reach the host can use the placeholder there, so the placeholder is only useful during the fetch phase. Narrowing the policy after identity admission removes the host; afterwards the placeholder resolves nowhere. Repository code never runs while the repository host is reachable.
- An Azure DevOps PAT cannot be limited to one repository. The operator issues it read-only (`Code (Read)`), short-lived and limited to the needed organization and projects. GitHub uses an App installation token limited to the repository, also through a provider.
- The host's authoritative `GitSource` acquisition also needs the token. That runs in the trusted worker, which already owns credentials under the [architecture](../../architecture.md); `GitSource` capture itself stays offline.

These are claims about OpenShell, not yet verified against the pinned 0.1.3 source. The pinned SDK's `Provider` model has credentials, expiration times and credential handles; the substitution and endpoint-binding behavior must be confirmed in the pinned source before any live run. If the pinned release exposes the raw token to the workload, private repositories stay blocked: there is no fallback to a workload-visible token, which would contradict the no-workload-credential rule. Public repositories need no provider.

## Acceptance and validation

Offline checks: recipe tokens and configuration are fixed and operator-owned; receipt parsing refuses missing, extra or malformed identity lines; host comparison refuses commit or tree mismatch; policy documents grant exactly one host and port and the narrowed revision grants none; provider configuration binds exactly the repository host; receipts containing the token value are refused.

Live qualification, on two fresh admitted nodes with confirmed cleanup, for one public repository already captured on the host (JSPWiki parent and fix under PLAN-0021 is the first candidate): matching identity passes; a deliberately wrong expected commit and a wrong expected tree are refused; a second host is denied during the fetch phase; the repository host is denied after narrowing, with a native denial event; a fetch interrupted by deleting the sandbox leaves no reused state; a repository fixture with a hook, a submodule and an LFS pointer runs none of them. For a private Azure DevOps repository: the fetch succeeds through the provider; the workload environment and filesystem hold only the placeholder; the placeholder sent to a second host is refused (`credential_endpoint_mismatch` or a policy denial) and never resolved; after narrowing, a request to the repository host with the placeholder is denied. Record fetch bytes, time and file count. Missing telemetry is unknown, not zero.

This spec does not qualify dependency resolution, builds, test discovery or any application observation. It does not resolve ISSUE-0006's general transfer criteria.

## Decisions and open questions

The user chose in-sandbox fetch over host-to-sandbox tree upload, then resolved the open questions on 2026-10-12: Azure DevOps is assumed to serve fetch by exact commit; private repositories are allowed with the PAT held by OpenShell's credential proxy; dependencies come from standard public registries under SPEC-0026. Default choices made here: shallow fetch by exact SHA, host capture stays authoritative, discard and recreate instead of retrying in place, no fallback to a workload-visible token. Remaining verification before any live run: confirm provider placeholder substitution and endpoint binding in pinned OpenShell 0.1.3 source.
