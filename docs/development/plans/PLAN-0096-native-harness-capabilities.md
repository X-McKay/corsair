---
id: PLAN-0096
kind: plan
title: Native Harness capabilities
status: complete
updated: 2026-10-14
related: [SPEC-0081, SPEC-0080, PLAN-0095, ISSUE-0009]
---

# Native Harness capabilities

## Objective and dependencies

Implement accepted [SPEC-0081](../specs/SPEC-0081-native-harness-capabilities.md): native Skills for current roles and a bounded capability reuse audit, preserving packages and typed authority. Root verified Harness0.55.0/core2.55.0 compatibility; dependency pin/install and installed native API checks precede implementation. Initial tests/evals are host-only outside OpenShell workflow. Prior simplification receipts remain bound to their source; live baselines are user-deferred.

## Steps

- [x] Pin/install the verified native Harness skills dependency and inspect installed APIs/resources without claiming runtime admission.
- [x] Adopt native Skills across roles from owned skill files, retaining static manifest boundaries and explicit Python tools/validators/budgets; test actual discovery/loading and changed native offers.
- [x] Audit existing native capability reuse, including delegation/review possibilities; record concrete choices and authority limits. Do not enable full Coder defaults or broad delegation.
- [x] Run host factory/contract/skill checks, scripted isolated suites and typed direct/Temporal fixture checks with actual receipts and source identities.
- [x] Keep OpenShell integration/admission/cleanup and live model quality separate; record unrun gates and update docs/CURRENT. Review final scope and prepare handoff after actual results.

## Validation and progress

Acceptance checkpoint only: implementation and validation **PENDING**. Root reports verifying public Harness0.55.0 requires core2.55.0; this is dependency research, not installed native skill behavior, composition or sandbox qualification. Documentation guards are separate from implementation evidence. No live evaluations or endpoints are invoked by this documentation lane.

## Decisions and next action

Prefer out-of-box native Harness capability reuse while retaining current full package structure. Native Skills owns loading/disclosure of trusted owned procedure files; do not build another loader or SDK-agnostic layer. Native Temporal and OpenShell are existing explicit boundaries, not automatic authority expansions. Root proceeds with dependency/native Skills implementation and delegated capability review, then records actual host checks. Stop on broadened authority or unsupported native behavior; continue independent authorized work. Keep exactly two probes and outcome-blind review unchanged.

## Readable agent-local native dataset amendment

The user-linked [probe-author dataset](https://github.com/X-McKay/infosec-harness/blob/feature/claude-refactor/src/infosec_harness/agents/probe-author/evals/dataset.yaml) was read through the public GitHub contents API:319 lines, version2, named smoke/capability/adversarial cases with category/scenario annotations and explanatory comments. Borrow its readable organization and close-to-agent location, not its custom payload/expected schema, marker protocol or target-name substring gates. Its own comments call trace/structural checks diagnostic and do not establish target attestation.

A bounded additive `src/corsair/agents/control_authoring/evals/dataset.yaml` pilot may use native Pydantic Evals `name`, `cases`, typed `inputs` and evaluator-only `metadata`, with two projections from existing frozen source-only fixtures. Native `Dataset[ControlInput, Drafted | Blocked, dict].from_file(...)` validates the existing contracts; no custom schema or loader. Category, provenance and expected checks stay in metadata outside agent-visible inputs. The evaluator passes only typed inputs to the production factory; labels, paired revisions and semantic/native outcomes never enter author context. Preserve original frozen files and baseline hashes, and retain existing standard CLI runners; no wholesale corpus move or new evaluation framework. The local example is readability/contract evidence, not promoted accuracy coverage. Root authorized the additive two-case pilot. `control_authoring/evals/dataset.yaml` now contains exact typed projections of the first two frozen parent cases; production `Drafted | Blocked` supplies the native output type. The focused native-from-file/input-equality/metadata-nondisclosure test and record guards pass6/6. Existing suites/data remain unchanged; this is a format pilot, not a new baseline.

## Implemented host checkpoint

Harness0.55.0 skills extra is pinned/locked and installed with unchanged core/evals2.55.0 and Temporal1.34.0. All seven factories use native Skills with explicit trusted libraries and a primary read-only package LocalWorkspace. No general filesystem/shell tools or full Coder/delegation defaults were added. Eight standard-frontmatter skill files retain their procedure bodies; prompt/config versions identify changed disclosure. Domain toolsets and output schemas remain intact; native load_capability is additional metered authority. Receipts include SDK versions and actual completed capability IDs (unknown when messages are omitted), and eval counters record actual activation calls.

Native progressive/package checks13 passed; primary/read-only/per-run/durable-operation checks initially3 passed, with an additional hard-cap regression passed at final review. Durable operation dispatch uses a host double; there is no new server/replay claim. Peer audit found no authority expansion or fabricated activation. PrepareTools withdraws domain tools while the reserved loader may remain visible; native UsageLimits still rejects the excess call before execution. See [capability audit](../../qualification/harness-capability-reuse.md).

Scripted isolated checks passed: environment8/8, identification8/8, planning5/5, author development8/8 each, author multilingual transfer8/8 each, validity7/7 and final-unit4/4; reviewed fixture chain5/5. All use real native loading. Two initial evaluator-only runs failed because activation was classified unknown (environment0/8) and counted as an evidence read (final0/4); corrected versioned runs pass and failed private reports remain. ID/planning isolated allowances explicitly increased by one request/tool for activation; production input-derived budgets were unchanged. Generated source was not executed on the host; native outcomes in the fixture route use only exact operator-reviewed bytes.

Full offline attempts were preserved: first222failed2104passed6skipped due former eager-body/test assumptions; after native test activation updates,1failed2326passed6skipped due an obsolete environment prompt-version assertion; corrected full suite **2327passed6skipped10warnings51.92s**. Final focused environment/fixture/dataset/records checks41passed; final progressive/readonly/hard-cap/package/dataset/records checks23passed. Wheel built offline and18 final manifest/skill/policy/dataset assets byte-match source. Record checks and diff validation are separate from runtime admission.

The two-case agent-local native dataset is an additive readability/typed-format pilot only, not a new model baseline or migrated default runner. Existing frozen corpora retain their identities. Fresh live model baselines remain user-deferred. Temporal service/replay and OpenShell integration/admission/cleanup remain separate unrun qualification boundaries. ISSUE-0009 remains open. No model endpoint calls or cluster operations occurred.
