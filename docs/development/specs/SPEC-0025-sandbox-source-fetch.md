---
id: SPEC-0025
kind: spec
title: In-sandbox pinned source fetch
status: draft
updated: 2026-10-12
related: [IDEA-0004, ISSUE-0006, SPEC-0006, SPEC-0010, SPEC-0011, SPEC-0012, PLAN-0021]
---

# In-sandbox pinned source fetch

## Goal and scope

The environment agent and every later execution stage need a real project's complete source tree inside a sandbox. Host-to-sandbox tree transfer is blocked by [ISSUE-0006](../issues/ISSUE-0006-native-transfer-retry-admission.md): pinned OpenShell 0.1.3 retries whole transfers after possible mutation and offers no pre-extraction byte, member or inode bound. The user selected a different route on 2026-10-12: the sandbox fetches the source itself from the hosting service with read-only access, and nothing is pushed back. This spec defines that fetch as the specifically reviewed narrower contract ISSUE-0006 allows. It is a deterministic node, not an agent.

In scope: one public GitHub or Azure DevOps repository fetched over HTTPS at one exact commit into a fresh sandbox, verified against the host's own immutable capture before any repository code runs. Excluded: private repositories and any workload credential, submodules, Git LFS, dependency or registry access (a separate spec), writes, commits, pushes, and any change to the general transfer criteria of ISSUE-0006.

## Boundaries and design

**Two copies with separate roles.** The host capture from `GitSource` (SPEC-0012) remains the authoritative `SourceSnapshot` with `commit` and `tree`. The sandbox clone is a working copy admitted only when its native commit and tree identities equal that snapshot. Agents keep reading the host capture; the sandbox copy is what the build and tests execute.

**Fetch recipe.** Operator-owned and fixed, run with the admitted toolchain image's pinned `git` before any repository content is executed: initialize an empty directory; `git -c core.hooksPath=/dev/null -c protocol.allow=never -c protocol.https.allow=always -c transfer.fsckObjects=true -c submodule.recurse=false fetch --depth=1 --no-tags <url> <commit>`; check out that commit with LFS smudge and all filters disabled; then print `git rev-parse HEAD HEAD^{tree}` and the tracked file count to stdout. Git clone and fetch do not run repository hooks, and the configuration above also refuses non-HTTPS transports, submodule recursion and filters. Fetching by exact SHA must be checked per host: GitHub serves reachable commits by SHA; Azure DevOps support is verified before that host is admitted.

**Identity admission.** The bounded stdout receipt from the existing execution adapter (SPEC-0010) is compared on the host with the `SourceSnapshot`. Any mismatch, missing field, extra output or nonzero exit refuses the sandbox for execution. The values are produced inside the sandbox, but only the pinned image's `git` has run there by then, so they are as trustworthy as the admitted image. After repository code runs, the working copy is untrusted. Later stages use the existing staging-copy and before/after integrity contract for that.

**Network phases.** The sandbox starts with a policy granting only HTTPS to the single repository host, for the pinned `git` binary. Once identity admission passes, the native `policy set --wait` narrows the sandbox to deny that endpoint. Deny-by-default network was qualified in [SPEC-0006](SPEC-0006-openshell-policy.md), which already exercised narrowing and endpoint removal on a running sandbox, with loaded revisions observed. A new matching denial event must then be observed from inside the sandbox before any repository code runs. Stored but unloaded policy never counts.

**Retries and unknown outcomes.** The sandbox is disposable. A failed, partial or unknown fetch is never repaired in place: the sandbox is deleted with confirmed cleanup and a new one is created. That removes the ISSUE-0006 concern for this path, because there is no host-side extraction and the only bytes entering host storage are the bounded receipt.

**Limits.** Fetch wall time, sandbox storage and memory are operator budgets, enforced by the existing execution and sandbox limits rather than by trusting the repository. A fetch that exceeds them fails as `dependency` or `sandbox` layer with retained native detail, never as an application result.

**Credentials.** None. The first release fetches public repositories only. A private-repository token would be a workload credential; adding one requires an explicit, separately reviewed exception covering scope (GitHub App installation tokens can be limited to one repository and expire within an hour; Azure DevOps tokens cannot be limited to one repository), removal before repository code runs, and exfiltration risk.

## Acceptance and validation

Offline checks: recipe tokens and configuration are fixed and operator-owned; receipt parsing refuses missing, extra or malformed identity lines; host comparison refuses commit or tree mismatch; policy documents grant exactly one host and port and the narrowed revision grants none.

Live qualification, on two fresh admitted nodes with confirmed cleanup, for one public repository already captured on the host (JSPWiki parent and fix under PLAN-0021 is the first candidate): matching identity passes; a deliberately wrong expected commit and a wrong expected tree are refused; a second host is denied during the fetch phase; the repository host is denied after narrowing, with a native denial event; a fetch interrupted by deleting the sandbox leaves no reused state; a repository fixture with a hook, a submodule and an LFS pointer runs none of them. Record fetch bytes, time and file count. Missing telemetry is unknown, not zero.

This spec does not qualify dependency resolution, builds, test discovery or any application observation. It does not resolve ISSUE-0006's general transfer criteria.

## Decisions and open questions

The user chose in-sandbox fetch over host-to-sandbox tree upload. Default choices made here: public repositories only, shallow fetch by exact SHA, host capture stays authoritative, discard and recreate instead of retrying in place. Open: whether Azure DevOps reliably serves fetch by SHA at depth one; whether dependency fetch follows the same phase-then-deny pattern through an allowlisted registry mirror (expected, in its own spec); and whether a private-repository token exception is wanted at all.
