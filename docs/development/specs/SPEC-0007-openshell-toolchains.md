---
id: SPEC-0007
kind: spec
title: Native OpenShell toolchain qualification
status: accepted
updated: 2026-10-11
related: [PLAN-0008, SPEC-0006]
---

# Native OpenShell toolchain qualification

## Goal and scope

Qualify only native [Milestone 1E](../../openshell-milestone.md): Python 3.12/pytest and Java 17/Maven/JUnit 5 actual execution and distinguishable build, discovery, assertion and dependency diagnostics. The user authorized continuing after 1D. These trusted infrastructure fixtures do not validate a finding or application fix. 1F interruptions/limits/recovery, adapters, agents, Temporal and production tenancy remain excluded.

## Boundaries and design

Keep the admitted OpenShell/Agent Sandbox/Helm/kind/Kubernetes/Calico tuple unchanged. Select primary official Python and Maven Linux amd64 manifests, exact Python wheels and Maven plugin/JUnit versions. Explicit native Docker preparation warms dependencies outside OpenShell; retain upstream checksums, complete JAR/POM hashes and whole-image digest, Docker config and containerd manifest identities. Run offline builds first with no network grants. Native CLI upload/download and SDK execution retain original sandbox identity and host-owned receipts. No production wrapper or kubectl execution fallback.

Use the existing hard-requirement filesystem policy with only exact read-only toolchain/cache directories added. A separate Python dependency stage permits GET only to a fixed PyPI missing-package path and the exact pinned six wheel path on files.pythonhosted.org. TLS verification and native interception remain enabled. A controlled echo Service supplies an available-registry transport control and a separate Service at an unserved port supplies an admitted unavailable-registry diagnostic; retain native upstream and trusted ordinary-pod controls. No wildcard endpoints, attached providers, credentials or policy relaxation.

Each fresh node requires exact-node storage/kernel/CNI and gateway/identity controls. Original sandbox/CR/pod/PVC/PV, endpoint/gateway namespace, private/forward and cluster cleanup must be confirmed. Failed or unknown commands remain retained; no blind workload replay.

## Acceptance and validation

On each of two fresh clusters, execute one fresh Python and one fresh Java sandbox. Upload only fixed trusted project files and check their hashes. Require exact expected test identifier/count, zero skips and native JUnit output for passing tests. Deliberate syntax, no-discovery and assertion diagnostics must have their own native result and expected producing layer. The offline missing-artifact attempt must retain the selected Maven resolver's namespace-prefix restriction and DependencyResolutionException; it is not an OpenShell policy denial. Separately execute a fresh hash-checked six wheel installation with no cache, a permitted PyPI 404/resolver failure, and an admitted unavailable-registry diagnostic. Preserve timings, output bytes, SDK calls, upstream detail, source/artifact hashes and all failed attempts. Offline guards exercise report rejection before live dispatch; they cannot qualify the runtime.

## Decisions and open questions

Primary current releases still select OpenShell 0.1.3/Agent Sandbox 1.0.6; compatible Helm 3.22.0 remains admitted despite latest 4.3.0. Official Python 3.12.15 slim-bookworm and Maven 3.10.0 Temurin 17 noble amd64 manifests are selected, with pytest 9.0.2 and JUnit 5.14.4. Native client execution supports trust-bundle injection; use enforced REST GET policy without TLS bypass. The complete unchanged-source matrix now has two fresh-cluster passes with confirmed cleanup, as bounded in the qualification report. See [PLAN-0008](../plans/PLAN-0008-openshell-toolchains.md).
