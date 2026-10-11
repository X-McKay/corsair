---
id: ISSUE-0003
kind: issue
title: Initial Service controls can fail after fixture Pod readiness
status: resolved
updated: 2026-10-11
related: [PLAN-0005, SPEC-0001, PLAN-0006]
---

# Initial Service controls can fail after fixture Pod readiness

## Observed and expected behavior

On the admitted kind 0.33.0/Kubernetes 1.35.8/Calico 3.33.0 Linux amd64 tuple, the existing network fixture waits for all Pods Ready, then runs PodIP and Service controls. During 1C prerequisite revalidation, .runs/lifecycle-network-001/ failed the initial ingress Service GET with curl 7 after successful PodIP controls (1 failed/2 passed, 123.32s). On the second fresh node, .runs/lifecycle-network-003/ failed initial egress Service GET with curl 28 after successful PodIP controls (1 failed/2 passed, 124.70s). Both occurred before the affected policy was applied. All four fixture namespace cleanups were UID-checked and confirmed.

## Reproduction and evidence

A failed control blocks dependent work and cannot be interpreted as a policy denial. Source/pins/requirements were unchanged; first-node fresh fixtures .runs/lifecycle-network-002/ subsequently passed all controls/denials/rollback in 152.66s. Second-node 004 also failed both initial Service controls with curl 7 (2 failed/1 passed, 89.90s), both namespace cleanups confirmed. Native diagnostic .runs/service-readiness-diagnostic-001/ then exercised three new fixtures; all initial PodIP/Service GET/POST and extra Service controls passed with no configuration change, all UID-checked cleanups confirmed. Actual EndpointSlices/proxy configuration/logs retained; iptables minSyncPeriod is 1s. The diagnostic did not reproduce the failure. Final complete unchanged suite 005 passed all three tests in 150.33s with both UID-checked cleanups confirmed. This permits bounded second-node native lifecycle execution after actual CNI controls; it does not resolve this startup reliability issue. Native route/readiness/resource receipts and server logs remain in the ignored directories. The [Kubernetes v1.35 proxy reference](https://v1-35.docs.kubernetes.io/docs/reference/command-line-tools-reference/kube-proxy/) documents asynchronous minimum resync. At that earlier checkpoint root cause was unproven: Service/endpoint/proxy convergence was a hypothesis, not a diagnosed CNI defect. The qualification report must retain these failures even when a later run passes.

## Attempts and diagnosis

Before the PLAN-0006 investigation, three diagnostic fixtures did not reproduce the failure and the final complete suite passed. Native proxy timing makes convergence plausible, but that earlier investigation had no causal proof or network repair. Earlier failed controls and all cleanups remain retained. Instantaneous Service readiness after Pod Ready is not an admitted guarantee; the resolution below adds an observed prerequisite before strict controls.

## Resolution criteria and next action

In a separate bounded network-readiness investigation, retain actual EndpointSlice readiness, native proxy/controller diagnostics and request outcomes at the failed control. Establish the producing layer and use a supported prerequisite/convergence observation if warranted. Do not count failed initial requests as successful controls, weaken timeout/deny criteria, suppress attempts or change CNI/policy/artifact inputs just to pass. Requalify affected native controls/denials and cleanup before resolving this issue. No repair is implemented in the lifecycle slice; full startup reliability remains unqualified.

Investigation under [PLAN-0006](../plans/PLAN-0006-service-readiness.md) reproduced curl 7 with original source in .runs/readiness-baseline-001/. EndpointSlice Ready preceded actual proxy DNAT programming; native no-endpoints REJECT packet counters increased for both failed requests, then a fresh request succeeded once the route appeared. This establishes the producing layer in that reproduction. A fixture-only bounded native endpoint/Service readiness prerequisite is implemented; final-source two-fresh-cluster requalification passed: .runs/readiness-network-002/ (3 passed, 156.05s) and 003/ (3 passed, 157.96s), all fixture UID and cluster container-ID cleanup confirmed. The [focused record](../../qualification/service-readiness.md) retains exact observations, prior failures, pre-review pass and limits. Historical curl 28 remains individually unattributed.

Resolved for the bounded fixture admission boundary. The native 30-second prerequisite requires the original Ready endpoint and exact successful Service responses/log coverage from both probes. Every setup failure is retained; stale identities, unexpected results, unknown delivery or exhaustion block policy work. Fresh strict PodIP/Service GET/POST controls, repeated denials, rollback, pins and policy criteria are unchanged. Two final-source runs also retained setup curl 7 refusals before successful observations and fresh controls. Thirty offline guards pass. This establishes supported qualification sequencing rather than instantaneous routing or a diagnosis of every historical timeout. No CNI/platform repair, OpenShell integration or fleet reliability claim is made.
