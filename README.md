# Corsair

Corsair is a planned system for validating a reported security issue against an exact repository revision and, when available, a proposed fix. It produces reproducible tests and evidence for InfoSec review. Implementation proceeds through independently qualified components before the complete agent graph is connected.

Status: the ordinary-pod kind/Calico boundary and the remaining 1A Agent Sandbox installation/storage/native OpenShell kernel admission slice each passed on two clean clusters on the qualified Linux amd64 host. 148 offline checks pass (94 repository guards, 15 lifecycle, 14 execution and 25 artifact/source cases). See the [network record](docs/qualification/network-platform.md) and [admission record](docs/qualification/openshell-admission.md). The bounded [gateway/identity record](docs/qualification/openshell-gateway.md) also passed on two clean clusters with confirmed cleanup; the bounded [native lifecycle/execution/transfer record](docs/qualification/openshell-lifecycle.md) passed three repetitions on each of two fresh clusters with confirmed CR/pod/PVC/PV and cluster cleanup. The [Service readiness prerequisite](docs/qualification/service-readiness.md) passed on two fresh clusters with confirmed cleanup; the [native policy matrix](docs/qualification/openshell-policy.md) passed three complete fresh-sandbox repetitions on each of two fresh clusters with confirmed cleanup. The bounded [native Python/Java toolchain matrix](docs/qualification/openshell-toolchains.md) passed on two fresh clusters with confirmed cleanup. The [native interruption/limit/recovery matrix](docs/qualification/openshell-recovery.md) passed on two fresh clusters with confirmed immutable cleanup. Bounded native 1A–1F qualification is complete on this tuple; production reliability, the full application adapter milestone and agents remain unqualified. The first [typed lifecycle adapter slice](docs/qualification/openshell-adapter-lifecycle.md) now passed three real cycles on each of two fresh nodes, with confirmed cleanup.

ISSUE-0003 is resolved for fixture control admission. [ISSUE-0004](docs/development/issues/ISSUE-0004-native-admission-readiness.md) is resolved as a [bounded startup observation](docs/qualification/openshell-readiness.md): six native-default readiness samples passed on two fresh nodes, with waits from 8.014 to 142.237s. The earlier 120s was a local test budget without a recorded SLO; neither it nor the pinned API default 300s is an upstream guarantee. Historical native qualification retains its original source/budget. Each fresh runtime still requires actual storage/kernel/CNI/gateway admission and Ready. Milestone 2 admits create/readiness/delete and the [bounded execution/output/failure slice](docs/qualification/openshell-adapter-execution.md) with protected host receipts in an exclusive operator workspace. Execution passed three cycles on each of two new admitted nodes with full cleanup; worker resources require the qualified Linux/glibc 2.39 profile. The independent [local immutable artifact/source store](docs/qualification/local-source-artifacts.md) passed two actual-host matrices with fresh-process rereads and confirmed fixture cleanup. Application transfers are blocked on [native retry/resource admission](docs/development/issues/ISSUE-0006-native-transfer-retry-admission.md); sandbox storage integration, live worker/controller fault recovery and agents remain later work.

## Development across sessions

Start with [AGENTS.md](AGENTS.md) and [current work](docs/development/CURRENT.md). The [development workflow](docs/development/README.md) defines shared Codex/Claude skills, principles, record templates, reviews, and handoff prompts. Ideas, specs, plans, development issues and handoffs have stable IDs under `docs/development/`; existing system design docs remain authoritative. Offline workflow guards run with `make test-config` and in GitHub Actions.

## Run the first slice

Requirements: Linux amd64, Python 3.12, `uv`, and a local Docker daemon capable of running privileged kind nodes and nested containerd workloads. These commands create a dedicated `corsair` cluster; they do not install into an existing cluster.

```shell
make tools
make test-config
make kind-up
make qualify-network
make kind-down
```

Setup and qualification are separate commands. Failed prerequisites produce errors, and evidence is retained under `.runs/`. Local ownership and kubeconfig state live separately under `.state/`. Both directories are excluded from Git. The [local platform runbook](docs/runbooks/local-platform.md) explains setup, failure diagnosis, and safe cleanup.

The remaining 1A admission commands and limitations are documented in the [admission runbook](docs/runbooks/openshell-admission.md). They install prerequisites and stage the trusted runtime probe without deploying a gateway. The [gateway runbook](docs/runbooks/openshell-gateway.md) adds an explicit node-admission-gated native installation and separate 1B probes. The [policy runbook](docs/runbooks/openshell-policy.md) stages a fixed canary artifact and runs the separately qualified native 1D matrix.

## Agreed decisions

- Deploy to Kubernetes; develop and test the complete configuration locally in kind.
- Use PydanticAI agents, native Temporal durability, OpenShell, Pydantic Evals, and supported OpenTelemetry integrations.
- Keep a fixed graph of five focused agents and deterministic evidence gates.
- Use small ports and SDK-backed adapters for external capabilities. Local model endpoints and Bedrock, and GitHub and Azure DevOps, must be interchangeable through explicit configuration.
- Support isolated agent execution with and without Temporal, and with fixture/local execution or OpenShell.
- Preserve scope, test validity, and application observations separately from sandbox enforcement.
- Use immutable artifacts, explicit invalidation, attributable failures, and tested recovery and cleanup.
- Measure outcomes, trajectories, consistency, grounding, robustness, security, durability, efficiency, and composition.
- Exclude repository-supplied environment hint files from the initial release. Discover setup from existing repository documentation, manifests, and CI.
- Keep analyst usefulness as a separate pilot proposal; it does not block the first technical milestones.

These incorporate improvement items 1, 2, 3, 4, 6, 7, 8, and 9. Item 10 is captured in the analyst pilot plan. Item 5 is outside initial scope.

## Reading order

1. [Investigation contract](docs/investigation-contract.md): supported scope, two tests, evidence, and conclusions.
2. [Architecture](docs/architecture.md): graph, agent boundaries, ports, and organization.
3. [Execution and recovery](docs/execution-and-recovery.md): modes, artifacts, invalidation, retries, cleanup, and failure attribution.
4. [Evaluation and acceptance](docs/evaluation-and-acceptance.md): evaluation types, datasets, metrics, and gates.
5. [Implementation plan](docs/implementation-plan.md): progressive milestones and required evidence.
6. [Analyst pilot plan](docs/analyst-pilot-plan.md): proposed measurement of practical InfoSec value.
7. [Benchmark datasets](docs/benchmark-datasets.md): researched sources, 50 candidate issue pairs, licensing, and progressive qualification across Java/Maven, Python, JavaScript, Perl, and Ruby.
8. [OpenShell milestone](docs/openshell-milestone.md): proposed directory structure, native runtime qualification slices, diagnostics, testing, and acceptance gates.

## Initial support envelope

The first qualification targets Python 3.12 with pytest and Java 17 with Maven and JUnit 5, on Linux OCI images in the selected OpenShell Kubernetes runtime. Actual tool versions and image digests are frozen during runtime qualification. Frameworks and vulnerability classes are admitted individually through real execution cases; a language label alone does not establish support.

The initial security cases are path traversal and command injection using bounded synthetic fixtures. Validation starts at component and application-path scope. Deployment-scope validation, additional runtimes, service-dependent findings, and other vulnerability classes require additional qualified fixtures. A local SSRF fixture is a later boundary-interference test, not an initial supported class.

## Design source references

- [Existing harness architecture](https://github.com/X-McKay/infosec-harness/blob/main/docs/architecture/TRIAGE_SYSTEM.md)
- [Zetra sandbox validation](https://github.com/X-McKay/zetra/blob/main/integrations/openshell-LIVE-VALIDATION.md)
- [Playbooks reference architecture](https://github.com/X-McKay/playbooks/blob/main/agent-playbook/02-reference-architecture.md)
- [OpenShell Kubernetes setup](https://github.com/NVIDIA/OpenShell/blob/v0.1.2/docs/kubernetes/setup.mdx)
- [PydanticAI Temporal integration](https://pydantic.dev/docs/ai/capabilities/durable_execution/temporal/)
- [Pydantic Evals](https://pydantic.dev/docs/ai/evals/evals/)

Implementation must pin compatible SDK and runtime releases. Upstream capabilities are not qualified merely by being documented.
