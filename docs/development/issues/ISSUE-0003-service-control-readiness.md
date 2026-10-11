---
id: ISSUE-0003
kind: issue
title: Initial Service controls can fail after fixture Pod readiness
status: open
updated: 2026-10-11
related: [PLAN-0005, SPEC-0001]
---

# Initial Service controls can fail after fixture Pod readiness

## Observed and expected behavior

On the admitted kind 0.33.0/Kubernetes 1.35.8/Calico 3.33.0 Linux amd64 tuple, the existing network fixture waits for all Pods Ready, then runs PodIP and Service controls. During 1C prerequisite revalidation, .runs/lifecycle-network-001/ failed the initial ingress Service GET with curl 7 after successful PodIP controls (1 failed/2 passed, 123.32s). On the second fresh node, .runs/lifecycle-network-003/ failed initial egress Service GET with curl 28 after successful PodIP controls (1 failed/2 passed, 124.70s). Both occurred before the affected policy was applied. All four fixture namespace cleanups were UID-checked and confirmed.

## Reproduction and evidence

A failed control blocks dependent work and cannot be interpreted as a policy denial. Source/pins/requirements were unchanged; first-node fresh fixtures .runs/lifecycle-network-002/ subsequently passed all controls/denials/rollback in 152.66s. Second-node 004 also failed both initial Service controls with curl 7 (2 failed/1 passed, 89.90s), both namespace cleanups confirmed. Native diagnostic .runs/service-readiness-diagnostic-001/ then exercised three new fixtures; all initial PodIP/Service GET/POST and extra Service controls passed with no configuration change, all UID-checked cleanups confirmed. Actual EndpointSlices/proxy configuration/logs retained; iptables minSyncPeriod is 1s. The diagnostic did not reproduce the failure. Final complete unchanged suite 005 passed all three tests in 150.33s with both UID-checked cleanups confirmed. This permits bounded second-node native lifecycle execution after actual CNI controls; it does not resolve this startup reliability issue. Native route/readiness/resource receipts and server logs remain in the ignored directories. The [Kubernetes v1.35 proxy reference](https://v1-35.docs.kubernetes.io/docs/reference/command-line-tools-reference/kube-proxy/) documents asynchronous minimum resync. Root cause is unproven: Service/endpoint/proxy convergence is a hypothesis, not a diagnosed CNI defect. The qualification report must retain these failures even when a later run passes.

## Attempts and diagnosis

Three diagnostic fixtures did not reproduce the failure and the final complete suite passed. Native proxy timing makes convergence plausible, but no causal proof or network repair exists. Earlier failed controls and all cleanups remain retained. Reliable immediate Service readiness is unqualified.

## Resolution criteria and next action

In a separate bounded network-readiness investigation, retain actual EndpointSlice readiness, native proxy/controller diagnostics and request outcomes at the failed control. Establish the producing layer and use a supported prerequisite/convergence observation if warranted. Do not count failed initial requests as successful controls, weaken timeout/deny criteria, suppress attempts or change CNI/policy/artifact inputs just to pass. Requalify affected native controls/denials and cleanup before resolving this issue. No repair is implemented in the lifecycle slice; full startup reliability remains unqualified.
