---
id: SPEC-0003
kind: spec
title: OpenShell installation and runtime admission
status: accepted
updated: 2026-10-11
related: [PLAN-0003, SPEC-0001]
---

# OpenShell installation and runtime admission

## Goal and scope

Complete only the remaining installation/storage/kernel subset of [Milestone 1A](../../openshell-milestone.md). The user authorized immutable artifact selection, supported native prerequisites and admission probes, attributable evidence, identity-checked cleanup, and publication of reviewed tracked changes. The published ordinary-pod boundary remains separate.

## Boundaries and design

Use the official Agent Sandbox core manifest and served v1beta1 API. Select the official OpenShell chart and matching images, render it offline, and defer gateway installation/identity to 1B. Run the release's native openshell-sandbox capability-probe in its standard workload image, staging the runtime from the separately pinned trusted image. Match the Kubernetes driver's non-root identity, zero capabilities, RuntimeDefault seccomp, no-new-privileges, strict groups and required namespaced sysctl. Do not supply bootstrap credentials, providers or a gateway. A native Sandbox and its generated pod establish the controller path; a PVC write/remount/read establishes actual storage behavior. Kind's existing local-path provisioner is local-only storage.

No custom kernel probes, supervisor copies in workload images, extra capabilities, host mounts, TLS bypass, policy changes or fallback profiles. Native admission itself fails closed before workload launch. Gateway, application adapters, agent and durable work remain outside this component.

## Acceptance and validation

Checksum-verified native artifacts; locked served API compatibility; offline Helm render with only discovery preflight disabled; smallest repository guards before live work. Live checks require Ready controller, bound PVC with retained identity and write/remount/read, successful native kernel probe output under the actual driver profile, and identity-checked namespace/PV/cluster cleanup. Repeat admission on a second fresh cluster for qualification. Preserve every failed command and upstream detail under ignored .runs/, credentials and ownership only under .state/. Missing or failed mandatory evidence blocks admission and later integration. Probe success qualifies primitives, not authenticated boundary service or gateway identity.

## Decisions and open questions

Source inspection selected OpenShell v0.1.3 and Agent Sandbox v1.0.6. Helm v3.22.0 follows the setup/support documentation's Helm 3.x requirement; upstream mise uses Helm 4.2.0 but that does not establish this local tuple. Immutable image and archive references are recorded in deploy/runtime-lock.yaml. Historical raw evidence is absent in this checkout; the published record and source were verified against origin/main, without claiming re-audit of absent logs.
