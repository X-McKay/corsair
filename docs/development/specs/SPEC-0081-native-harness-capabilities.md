---
id: SPEC-0081
kind: spec
title: Native Harness capabilities
status: accepted
updated: 2026-10-14
related: [SPEC-0080, PLAN-0095, PLAN-0096, ISSUE-0009]
---

# Native Harness capabilities

## Goal and scope

Use native PydanticAI Harness capabilities with Temporal and OpenShell while preserving the full Corsair agent-package structure and narrow domain contracts. Initial scope is native Skills adoption across current roles and an audit of existing native capability reuse. Initial testing and isolated evaluation run on the host, outside the OpenShell workflow, with typed ports and deterministic fixtures. User-deferred live baselines remain deferred.

## Boundaries and design

Harness0.55.0 skills extra is pinned and installed with its exact required PydanticAI core2.55.0. Verify installed APIs and supported behavior before implementation claims. Keep fixed trusted package manifests, explicit Python capability authority, typed contracts/output validators and provenance. Owned skill files remain authoritative procedure sources; native Skills supplies disclosure/loading rather than a custom loader or duplicated eager instruction text. Preserve exact content and dependency authority; record intentional native offer changes separately from parity claims.

Audit native capability facilities before adding bespoke code, including their interaction with current tools, budgets, direct execution and native Temporal durability. Delegation/review capabilities are subjects of the audit, not blanket new tool authority. Do not adopt full Coder defaults, unrestricted execution or delegation. No SDK-agnostic abstraction, Google adapter or generic orchestration framework is in scope.

Temporal retains typed workflow payloads and the existing direct/durable contracts. OpenShell execution stays behind its admitted integration ports; installation, host fixture tests and isolated evals do not qualify a live sandbox, cleanup or complete workflow. Exactly two native probes, independent authors and immutable outcome-blind validity remain unchanged. Operator policies stay immutable to investigated agents.

## Acceptance and validation

Verify native skill discovery/loading and precise offered authority in every current factory, preserving owned content and negative rejection boundaries. Test dependency/output contracts and native capability composition on the host without executing generated code. Run affected scripted isolated suites, typed/direct fixture checks and proportionate Temporal checks; preserve previous receipts and record source/spec/skill/tool/factory/policy identities, effective settings, retries and unknown telemetry. Record changed skill disclosure as a versioned change; structural success is not semantic qualification.

OpenShell integration/admission/cleanup and live provider/model quality remain separate progressive gates. Do not relabel mocked observations as execution or count dependency installation as admission. Implementation and host checks are recorded in PLAN-0096; live model/service/sandbox qualification remains distinct.

## Decisions and open questions

The user explicitly requests taking full advantage of native Harness, Temporal and OpenShell while keeping initial tests/evals host-only. [PLAN-0096](../plans/PLAN-0096-native-harness-capabilities.md) owns implementation. Native API details, capability reuse choices and effective offer changes must be verified against installed source. SDK-agnostic exploration and user-deferred live baselines remain deferred; no new authority follows automatically from a native default.

## Readable agent-local native dataset amendment

The user-linked [probe-author dataset](https://github.com/X-McKay/infosec-harness/blob/feature/claude-refactor/src/infosec_harness/agents/probe-author/evals/dataset.yaml) was read through the public GitHub contents API:319 lines, version2, named smoke/capability/adversarial cases with category/scenario annotations and explanatory comments. Borrow its readable organization and close-to-agent location, not its custom payload/expected schema, marker protocol or target-name substring gates. Its own comments call trace/structural checks diagnostic and do not establish target attestation.

A bounded additive `src/corsair/agents/control_authoring/evals/dataset.yaml` pilot may use native Pydantic Evals `name`, `cases`, typed `inputs` and evaluator-only `metadata`, with two projections from existing frozen source-only fixtures. Native `Dataset[ControlInput, Drafted | Blocked, dict].from_file(...)` validates the existing contracts; no custom schema or loader. Category, provenance and expected checks stay in metadata outside agent-visible inputs. The evaluator passes only typed inputs to the production factory; labels, paired revisions and semantic/native outcomes never enter author context. Preserve original frozen files and baseline hashes, and retain existing standard CLI runners; no wholesale corpus move or new evaluation framework. The local example is readability/contract evidence, not promoted accuracy coverage. Root authorized the additive two-case pilot. `control_authoring/evals/dataset.yaml` now contains exact typed projections of the first two frozen parent cases; production `Drafted | Blocked` supplies the native output type. The focused native-from-file/input-equality/metadata-nondisclosure test and record guards pass6/6. Existing suites/data remain unchanged; this is a format pilot, not a new baseline.
