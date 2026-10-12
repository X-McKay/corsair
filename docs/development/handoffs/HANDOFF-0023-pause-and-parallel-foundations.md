---
id: HANDOFF-0023
kind: handoff
title: Pause and parallel foundation continuation
status: recorded
updated: 2026-10-11
related: [SPEC-0011, PLAN-0013, ISSUE-0006, SPEC-0010, PLAN-0012, PLAN-0014]
---

# Pause and parallel foundation continuation

## Verified state

### Latest user direction and pause

After completing bounded untrusted-file qualification, the user asked to start Temporal and PydanticAI development with sub-agents in parallel while OpenShell qualification continues. Before delegation began, the user requested this comprehensive handoff and a break. **No Temporal/PydanticAI sub-agent, installation, dependency edit, implementation, model call or service was started.** Resume that authorized parallel work when the user continues; do not run it during the break.

This is a continuity snapshot, not a new qualification receipt. [HANDOFF-0022](HANDOFF-0022-openshell-untrusted-file-qualified.md) remains the immutable snapshot of the completed file qualification. [CURRENT](../CURRENT.md) identifies this handoff for resumption. This pause adds documentation only; no live operation is pending. The three previous qualification agents have completed and are idle.

### Git and publication

Workspace: `/home/al/git/corsair`. Branch: `codex/openshell-untrusted-output`. Starting HEAD and published qualification revision: `7cf6d8ee44a77e5510cdd15bf2836de681d741e7`, subject `Qualify bounded untrusted-file collection through native execution`. Its parent is `52d3ff4592fd74ac4f7dfb8706215d28b8fea658`.

At pause preparation, native GitHub reads freshly confirmed [PR16](https://github.com/X-McKay/corsair/pull/16) is open/draft at exactly `7cf6d8ee44a77e5510cdd15bf2836de681d741e7`, head `codex/openshell-untrusted-output`, base `codex/openshell-parallel-admission` ([PR15](https://github.com/X-McKay/corsair/pull/15)). PR16 is a stacked draft, not a change based directly on main. Preserve the stack and verify parent state before future publication; no merge is authorized.

[Development CI 38196660359](https://github.com/X-McKay/corsair/actions/runs/38196660359) is completed/success for that exact head. The actual `offline-guards` job log records 148 checks passed in 6.73s. CI is offline validation, not live OpenShell or Temporal qualification. Its successful head does not automatically cover a later documentation or implementation commit.

The working tree was clean before this handoff. This pause prepares this new handoff, the CURRENT pointer/focus and a PLAN-0013 publication/continuation note locally; their final Git/publication state must be inspected on resume. Resolve any later commit containing this document using `git log -- docs/development/handoffs/HANDOFF-0023-pause-and-parallel-foundations.md`; do not substitute an invented future SHA. Original private evidence stays ignored and is not part of the published ten-file qualification commit.

### What exists in source

The repository currently implements narrow sandbox lifecycle/execution ports and OpenShell adapters, immutable ArtifactRef/SourceSnapshot contracts, LocalArtifacts, GitSource and protected host receipt storage. See `src/corsair/ports/` and `src/corsair/adapters/`; inspect actual source rather than assuming proposed architecture folders exist.

There is no implemented Temporal workflow, PydanticAI agent factory, provider factory, complete investigation graph or production report consumer. Current `pyproject.toml` development dependencies are pytest, PyYAML and the pinned OpenShell wheel; Temporal and PydanticAI dependencies are absent. No compatible Temporal/PydanticAI version tuple has been selected or verified. Do not use release/version guesses from this handoff as pins.

## Validation and blockers

### Qualified foundation and its limits

| Boundary | Verified scope | Authoritative record |
| --- | --- | --- |
| Native platform/OpenShell 1A–1F | Selected single-node Linux amd64 tuple; actual admission/enforcement/recovery controls and cleanup | [Current foundation index](../CURRENT.md), [recovery](../../qualification/openshell-recovery.md) |
| Lifecycle and bounded execution adapters | Operator-exclusive workspace; selected Linux/glibc worker; bounded outputs, worker/receipt faults | [Lifecycle report](../../qualification/openshell-adapter-lifecycle.md), [execution report](../../qualification/openshell-adapter-execution.md) |
| Immutable source/artifact storage | One exclusive local root and complete offline bare Git input | [Local storage report](../../qualification/local-source-artifacts.md), [PLAN-0014](../plans/PLAN-0014-immutable-source-artifacts.md) |
| Native trusted upload and fixed source arrival/execution | Reviewed disposable upload and fixed stdlib fixture; exact inputs/outputs and original cleanup | [Upload](../../qualification/openshell-native-upload.md), [arrival](../../qualification/openshell-source-upload.md), [execution](../../qualification/openshell-source-execution.md) |
| Original-forward transport loss | Unknown execution retained without replay; original owned cleanup | [Transport report](../../qualification/openshell-execution-transport.md), [PLAN-0012](../plans/PLAN-0012-sandbox-execution-adapter.md) |
| Bounded untrusted-file collection | Fixed inert exclusive regular file, at most 4096 bytes, existing raw execution/artifact composition | [File report](../../qualification/openshell-untrusted-file.md), [SPEC-0011](../specs/SPEC-0011-native-transfer-admission.md), [PLAN-0013](../plans/PLAN-0013-native-transfer-admission.md) |

These are bounded results, not full Milestone 2 or production reliability. Every fresh live OpenShell runtime still requires actual current-node storage/remount/kernel/CNI/gateway admission. A saved passed report cannot admit a different node or altered runtime/policy.

The latest file case uses a fixed isolated inline Python reader and supported raw `ExecChunk.data` through OpenShellExecution into LocalArtifacts. It does not use CLI archive download or SDK ExecResult text, which replaces invalid UTF-8. Original O_PATH/no-follow descriptors admit root/file identity, regular type, link count, owner and size before I/O. The reader buffers cap+1, checks observed stamps/anchors before output and treats content as opaque bytes. Only acknowledged terminal exit zero, original worker reap, exact fixture bytes and protected intent/result bindings permit publication. Failure, partial output or unknown delivery never publishes or blindly replays.

No archive/parser/transfer API/runner/protocol/retry framework or production consumer was added. The selected sandbox is inert and exclusive. Before/after identity/stamp observations do not establish an atomic snapshot or detect all transient changes. Arbitrary writers/environments/recipes remain unqualified. Isolated Python does not itself remove Bash startup variables; actual empty user/template/provider configuration and the reviewed native startup environment are part of this narrow admission.

### Latest actual live results

| Fresh node | Mandatory storage/kernel | CNI | Fixed file matrix |
| --- | --- | --- | --- |
| 001: `daf42d55-be67-47ce-a9e6-1dc49432f33e` | 1 pass / 92.510s | 3 pass / 156.451s | 1 pass / 97.323s |
| 002: `310a388b-ca08-49ff-9180-31e8fa522fa2` | 1 pass / 92.507s | 3 pass / 157.591s | 1 pass / 128.958s |

Each node passed storage remount/marker retention across distinct Ready pods using the original PVC/PV, all mandatory kernel flags including Landlock ABI6, CNI controls and the exact-node gateway installation. Actual mTLS/trust/hostname, unauthenticated gRPC and six interleaved outer-fence denial/reachable controls passed per node.

Each file matrix passed four exact positive controls (empty, binary/non-UTF8, exact cap, hostile literal basename) and ten refusals (oversize, sparse, directory, FIFO, symlink, hardlink, replaced entry, wrong root, root symlink, replaced root). Seven host selection guards refused before SDK/intent creation. Nine native refusals require exit65 with empty output; root symlink alone requires exit66 with exact errno20 diagnostic. Policy denial, EACCES, deadline or unknown execution cannot substitute for these structural refusals.

Across the two nodes: 28 acknowledged terminal/reaped worker executions; eight admitted artifacts and 20 strict refusals; 14 host guards; 56 recorded worker SDK method starts; 26 helper SDK records (24 acknowledged and two expected post-delete NOT_FOUND reads with unknown completion); 187 file-matrix native commands. Collected stdout: 10,276 bytes; expected refusal stderr: 26 bytes. Total measured worker time: 2.773500s; peak host worker RSS: 111060/112232KiB. Native internal retries/polls/RPCs and remote reader RSS remain unknown. Application retries were zero; no model/provider calls occurred.

The four artifacts per node have identical size/digest identities. A fresh host process reread them after original sandbox cleanup. Separate host corruption was refused by real get/put. The corruption fixture captures dev/inode/UID, but its explicit cleanup assertion compares dev/inode and checks removal; do not invent a separate current-UID assertion or host exception trace. Protected composition results were not separately reopened by another process.

### Immutable source and cleanup

Both counted file matrices use unchanged source-v2 with 72 frozen inputs:

- Manifest SHA256: `4f657f9e61593bc2fb43a03008446e211c0b370baa5d9aef742929af130fe457`.
- Case SHA256: `a924bcada2628e9691abb0e82bc9ad59d46ba9c6b4df8be16d542c1d51817f6f` (`tests/qualification/test_untrusted_file.py`, 248 lines).
- Reader SHA256: `e0c5ab0c2780d023dcee51ffbb63bad5e64a01b3b3309efdbd8a1b24d7b9170f`.
- Paired raw audit SHA256: `5022c911463f84b49db3bf4b257170376629d26fa1465fb3fe7af5f78bf54040`; verdict `two_node_raw_verified`.

Source-v1 and all earlier preparation evidence remain retained. V1 had no file dispatch. Final startup review added only ordinary Bash PWD/OLDPWD/SHLVL/_ to two proposed allowlists; all other 71 inputs and mandatory gate/runtime inputs are identical. Both counted file runs use v2, without later source edits. The pause freshly rechecked all 72 current input bytes against v2; they match.

Original application sandbox IDs `6f778e9d-84b6-403e-8784-71e7a2d7b3e4` and `8a0a2e94-c493-49d9-89c7-fea78f9eed46`, CRs/pods/PVCs/PVs/container tasks, gateway namespaces/private credentials and original forwards have confirmed cleanup. Original cluster CIDs have immutable-ID native absence receipts:

- Node001: `a3edcaa429d190a6c1b17b01c5188f954313a0ab591c98701c0c6c9224f37fc5`.
- Node002: `f765d45b49b28bbeb1ea9bec92fc9b50c69bcbb0cc1ff053cad4e64d645e4332`.

Node001 was removed before node002 admission. Final inventories contain exactly six platform namespaces and no sandbox/PV. Original forward Popen objects were reaped with exit−15 and independent /proc absence observations. Do not invent original process start ticks. No active kind owner/kubeconfig or OpenShell private state remains. Cleanup claims are supported by original receipts and paired audits; this documentation-only pause did not recreate or re-run the clusters.

### Private evidence and reproduction of review

All paths below are repository-relative and ignored. Keep the originals; do not upload raw logs, source exports, objects or credentials into Git.

| Evidence | Location |
| --- | --- |
| Original file/SDK/native command/JUnit/artifact/receipt data | `.runs/untrusted-file-host-001` and `-002` |
| Current-node mandatory admission | `.runs/untrusted-file-admission-001` and `-002` |
| Actual CNI controls/cleanup | `.runs/untrusted-file-network-001` and `-002` |
| Gateway install receipts | `.runs/gateway-install/c6efd5fb04ae4fa2adb8560a1ed87504` and `72274d00d5d8437f848aa302309ee309` |
| Root freeze, ownership, final inventories, exact-CID absence and publication receipts | `.runs/untrusted-download-review-20261011/root` |
| Primary immutable source/help/release review and file raw auditor | `.runs/untrusted-download-review-20261011/upstream-agent` |
| Contract/source/final record review | `.runs/untrusted-download-review-20261011/contract-agent` |
| Independent mandatory/gateway/cleanup and runtime/convergence audits | `.runs/untrusted-download-review-20261011/adversarial-agent` |
| Fresh pause PR16/CI verification | `.runs/pause-handoff-20261011` |

Useful exact files include root `source-v2.json` and its `source-v2/` snapshot, `file-run-context.json`, `paired-raw-audit.json`, `publication-completion.json`, `published-ci-final.json`, `published-ci-job.log`; upstream `file-independent-untrusted-file-host-001-untrusted-file-host-002.json`; contract `final-record-review.json`; adversarial `paired-admission-gateway-cleanup-audit.json` and `paired-runtime-convergence-audit.json`. Derived audit summaries are navigation aids; original receipts/JUnit/object bytes/frozen source remain the proof. If evidence is absent in a new checkout, mark that verification unavailable instead of reconstructing proof from prose.

Safe read-only checks, from the repository root:

```sh
git status --short
git branch --show-current
git log -3 --oneline
python .runs/untrusted-download-review-20261011/root/check_frozen.py \
  .runs/untrusted-download-review-20261011/root/source-v2.json
PYTHONPATH="$PWD/src:$PWD" UV_CACHE_DIR="$PWD/.cache/uv" UV_OFFLINE=true \
  uv run --locked python \
  .runs/untrusted-download-review-20261011/upstream-agent/audit_file_matrix.py \
  .runs/untrusted-download-review-20261011/root/source-v2.json \
  .runs/untrusted-file-host-001 .runs/untrusted-file-host-002 \
  --context .runs/untrusted-download-review-20261011/root/file-run-context.json
UV_OFFLINE=true make test-config
```

The private raw auditor is a retained review tool, not a new production framework. Inspect it before reuse. Later authorized source/dependency changes may correctly differ from the historical freeze; audit the historical snapshot and published revision separately from the new candidate rather than calling that old qualification invalid or silently updating its manifest.

### Known operator/tool details

`make test-config` already uses the repository uv cache by default. Direct uv commands should explicitly set `UV_CACHE_DIR="$PWD/.cache/uv"`; the home cache is read-only in this session. Private scripts importing repository code need `PYTHONPATH="$PWD/src:$PWD"`. Keep these invocation corrections separate from native runtime admission. Host Bash probes exposed host Nix startup injection and did not qualify that environment; do not expand native allowlists to fit host-specific names.

The actual native gateway ownership file is `.state/openshell/owner.json`, not gateway-owner.json. Its schema has no assumed cluster_container_id field. Read actual ownership schemas, bind current kind/admission/node identities and preserve original ownership copies before cleanup. A failed evidence copy after successful installation must not trigger another installation. Git metadata writes may need the environment's escalation mechanism; this is not new user authorization.

The installed `gh pr edit` path previously failed on an obsolete ClassicProjects/projectCards GraphQL field. Structured REST PATCH of the existing pull request using `gh api --input` worked. For bodies, write exact Markdown/JSON to a private file rather than interpolate it through shell arguments. Always attach a newly created PR to the task with the app artifact tool, and verify native head/base/CI. Do not create another PR merely to record this pause.

### Failure history and open gates

No counted native file matrix failed or was replayed. Retained preparation failures include guessed read/import paths, read-only home uv cache/Git metadata access, host Bash/Nix startup probes before fixture creation, post-install ownership filename/field mistakes without installation replay, and private audit/metric extractor field-shape/time-label mistakes. Final report review corrected the corruption-cleanup UID wording. Actual CNI observations retain 24 strict negative curl28 results plus two initial denial-convergence timeouts per node, and one node002 pre-policy readiness curl7 before successful controls. Two expected original post-delete NOT_FOUND reads retain unknown completion. Failed attempts are not rewritten or discarded.

[ISSUE-0006](../issues/ISSUE-0006-native-transfer-retry-admission.md) and overall PLAN-0013 remain blocked. Pinned native CLI download extracts an archive before expected-file checks, without enforceable pre-extraction aggregate byte/member/inode bounds or supported retry-off/authoritative reconciliation. Four native whole-operation attempts remain in the pinned source. A digest after extraction, host deadline or trusted-download control cannot resolve this untrusted boundary.

General file/directory transfers, file-specific interruption/reconciliation, arbitrary recipes/environments, active writers/atomic snapshots, production consumers and broader controller/storage durability/cancellation remain unqualified. Full Milestone 2, deterministic two-test application validation, real model/provider compatibility, Temporal durability and the complete graph are not complete. Foundation fixture tests do not prove an application fix. Exactly two native issue-validation tests remain required: benign control and security safety regression; labels/oracles stay outside agent-visible inputs.

The last primary release review selected OpenShell0.1.3 at e1f3c82caa3ed3b65de22889ae7ef32a774878ef and Agent Sandbox1.0.6 at cd0761d5001baaf293460cd382ee318744d6b249. Qualified Helm3.22.0 and workload/image/SDK pins are unchanged; Helm4.3.0 was then latest. Releases were not researched anew for this documentation pause. Verify current primary sources before new implementation. Native readiness uses the supported300s default; the historical120s budget is not a gate or product SLO. Existing execution output4096/native2s/host20s/worker512MiB and kernel/TLS/policy requirements remain operator-owned.

## Decisions and next steps

### Resumption order and parallel assignments

Use the [development skill](../../../.claude/skills/corsair-development/SKILL.md), [review skill](../../../.claude/skills/corsair-review/SKILL.md) and [handoff skill](../../../.claude/skills/corsair-handoff/SKILL.md). Read [architecture](../../architecture.md), [implementation milestones](../../implementation-plan.md), [execution/recovery](../../execution-and-recovery.md), [investigation contract](../../investigation-contract.md) and [evaluation/acceptance](../../evaluation-and-acceptance.md) only as relevant to the chosen boundary. These remain authoritative; this handoff does not create another architecture.

First inspect source/Git/evidence and reconcile the current work records. Then delegate two bounded independent foundation tracks, leaving root to coordinate and continue one OpenShell boundary. Use sub-agents within this task, not new user-owned chats unless requested. Existing completed agent handles may be reused if available; a later session must not assume they still exist.

| Owner | First bounded objective | Deliverables and check boundary | Explicit dependency gate |
| --- | --- | --- | --- |
| Root / OpenShell track | Review one concrete approved generated-report consumer over the admitted execution/artifact path, or select one existing-adapter durability/cancellation case | Focused plan, exact authority/writer/input/output contract, smallest offline checks, then relevant fresh-node live qualification | No general archive/transfer integration while ISSUE-0006 remains blocked; choose one component rather than both options at once |
| Temporal sub-agent | Milestone3 native deterministic fixture foundation | Verify immutable supported Python SDK/local-service tuple; focused spec/plan; smallest parent/child workflow plus native activities; useful fixture failure/cancellation/replay checks | Fixture execution may proceed independently; persistent-service restart and real durability need actual native evidence. No OpenShell side-effect retries or full graph wiring yet |
| PydanticAI sub-agent | Milestone5 agent template and one read-only fixture stage | Verify immutable compatible native SDK/Evals/Temporal integration; focused spec/plan; typed inputs/outputs, factory, restricted fixture read tools, native TestModel/FunctionModel/overrides/limits and isolated evaluation | Deterministic model tests establish contracts only. Real endpoint/Bedrock calls, OpenShell-backed execution tools, live reasoning quality and direct/durable equivalence need separate admission |

These assignments are recommended starting slices within the user's authorized parallel development request, not already accepted detailed designs or implemented records. Each agent should reduce the slice if source/API review exposes an unresolved dependency. Create component directories only when that component is actually needed. At pause, no Temporal/PydanticAI record IDs or dependency versions are allocated; root must check and allocate distinct next-unused IDs before concurrent record creation.

### Coordination and native feature reuse

Root owns shared configuration/dependency lock, CURRENT, common contracts, live runtime mutations, final integration review and publication. Give each agent distinct source/test/record ownership and a private evidence directory. Because agents share this checkout, do not let them concurrently edit `pyproject.toml`, `uv.lock`, shared ports or runtime state. Use isolated managed worktrees if implementation genuinely requires separate dependency environments, with explicit paths and no assumed copying of dirty files. A simpler distinct-file/shared-lock workflow is sufficient when independent research and contract preparation need no isolation.

Resolve PydanticAI/Temporal SDK compatibility together before changing the shared lock. Use Context7 for discovery/current API lookup, then verify official primary documentation, immutable release artifacts/source and actual installed APIs. Keep existing OpenShell pins stable. Unknown compatibility is a blocker to the dependent code, not a reason to patch SDK internals or silently fall back.

Temporal owns workflow history, deterministic transitions, native retries/timeouts/cancellation/versioning/replay. Workflow code performs no file/network/model/OpenShell I/O. Start with fixture activities; persistent local service qualification must use a supported configuration with owned state and cleanup evidence, distinct from production infrastructure. Do not create another job ledger, scheduler or generic graph engine. Choose retry ownership per operation; an unknown sandbox dispatch cannot be made safe by wrapping it in a retryable activity.

PydanticAI owns agent loops, structured outputs, limits, native provider objects, overrides, toolsets and instrumentation; Pydantic Evals owns evaluation execution/reports. First establish one read-only component (issue analysis is the architecture's first agent), not all five agents. Agents receive explicit saved stage inputs and separate context. Keep trusted expected labels/oracles outside those inputs, narrow tool authority and operator-injected budgets. Fixture models must also use fixture tools; mock model selection alone cannot prevent real side effects. Read-only analysis needs no command executor or unqualified sandbox.

Reuse the same agent factory/contracts for direct and eventual native Temporal execution. Verify the supported PydanticAI Temporal integration before implementing durable model/tool scheduling; do not wrap the whole agent loop in one opaque retryable activity. Vendor SDK types stay in adapters/integration boundaries. History carries small typed state and authorized artifact references, with large source/output in storage; existing ArtifactRef dataclasses alone do not admit arbitrary artifact contents or authorize reads.

Required evidence evolves with the component: deterministic contract/negative checks, fixture trajectory/output/tool/usage limits and provenance first; native Temporal restart/cancellation/history replay and actual provider calls later. Measure latency, model/tool calls, retries, tokens and failure layers. Missing usage/tracing is unknown, not zero. Freeze baseline cases/settings before comparative agent changes; a small smoke suite does not establish production reliability or tail-latency thresholds. Native tracing/Evals reports should be used before any custom telemetry.

### Authorization and stopping conditions

The current user request authorizes independent Temporal/PydanticAI development in parallel on resumption; earlier instructions explicitly authorized sub-agents and tracked stacked draft publication. It does not waive progressive qualification. Keep full integration behind the actual required gates. Continue independent fixture/local work when an OpenShell gate is blocked; do not mislabel it live sandbox admission.

Do not weaken policies/TLS/pins/kernel/budgets, supply workload credentials/arbitrary host access, resume the withdrawn Docker transfer runner or invent a reconciliation/broker framework. Unknown side effects retain their original identity/evidence and are not blindly replayed. A failed benign control, skipped discovery, unknown execution or sandbox denial cannot prove an application fix.

Never commit `.runs/`, `.state/`, credentials or raw logs. No merge, deployment, external issue closure or messaging upstream is authorized. Do not create background automations to continue during the user's break. On substantial resumed work, review the final diff, update affected plans/issues/CURRENT, append a new handoff and publish only tracked authorized changes with native exact-head CI verification.

### Pause-only checks

Before this snapshot, qualification closing checks were 148 passed /4.55s locally, four final record guards passed /0.04s, staged diff/source checks passed, and published CI passed148/6.73s. Fresh pause checks confirmed clean starting Git, PR16/exact-head CI, completed prior sub-agents and unchanged72-input freeze. No new native runtime, provider or Temporal qualification was attempted for this handoff. The pause documentation guards passed all four checks in 0.04s using explicit repository UV_CACHE_DIR with UV_OFFLINE=true. Final root review checks record consistency, source-freeze preservation and the tracked diff; inspect the working tree before resuming.

## Continuation prompt

```text
Resume Corsair from docs/development/handoffs/HANDOFF-0023-pause-and-parallel-foundations.md. Read AGENTS.md, README.md, CURRENT and the Corsair development/review/handoff skills, then linked relevant plans/contracts and HANDOFF0022. Inspect branch/status/source/publication before editing; preserve local pause-doc changes. Verify published PR16/head7cf6d8e/CI38196660359 and the actual two-node qualification/raw cleanup against historical source-v2 when evidence is available; never accept a handoff as proof. The user authorized Temporal and PydanticAI foundation development with sub-agents in parallel while OpenShell validation continues, but paused before either track began. Once resumed, delegate one bounded Temporal deterministic fixture foundation and one bounded PydanticAI read-only agent-template/fixture-evaluation foundation. Root coordinates shared dependency compatibility/pins/lock/contracts/records/publication and one selected OpenShell report-consumer or durability boundary. Allocate distinct files/record IDs; do not concurrently mutate shared runtime/configuration. Use native supported SDKs/integration and primary immutable sources, with Context7 for discovery. Reuse the same agent factory/contracts direct/durable, native Temporal history/replay/cancellation, and PydanticAI/Evals limits/tools/instrumentation. No full graph, opaque retryable whole-agent loop, unsafe archive transfer, alternate runner, scheduler or generic repair framework. Fixture checks do not qualify native durability/providers/OpenShell. Keep ISSUE0006/general extraction/reconciliation blocked and preserve operator policy/TLS/kernel/budgets/pins. Run smallest relevant offline checks, then actual admitted boundary tests; retain every failed/unknown attempt and original identity cleanup. Keep exactly two issue-validation tests and oracles outside agent inputs when that stage begins. Update records/CURRENT, review, append a new handoff and publish only tracked authorized draft changes; no private evidence, merge, deployment, external issue closure, messaging or unattended work during the break.
```
