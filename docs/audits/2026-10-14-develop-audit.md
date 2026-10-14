# Corsair `develop` technical audit

**Target:** [`bc3c25fa46686bdf3120b96caac174c39c8285af`](https://github.com/X-McKay/corsair/tree/bc3c25fa46686bdf3120b96caac174c39c8285af). **Status vocabulary:** “confirmed” below means source inspection or a deterministic local seam reproduction in the supplied workstreams; it does **not** mean that a provider, Docker workload, Temporal server, OpenShell runtime, corpus, or baseline suite was executed. Findings describe the base revision; the later delivery section distinguishes implemented fixes and measured validation from remaining recommendations.

## Moving-branch update: what changed while this audit ran

The main findings and original Qwen experiment refer to the explicitly pinned starting snapshot **`bc3c25fa46686bdf3120b96caac174c39c8285af`**, not an assertion that `develop` stayed unchanged. Before delivery, `develop` advanced to **`06d4cbe21b891051811f80559a478881c061ee86`**. The audit patch was rebased onto that integration snapshot, preserving concurrent work and its pins. Records were renumbered to **PLAN-0101 / HANDOFF-0137** because upstream used PLAN-0100 / HANDOFF-0136.

Important updates to the earlier findings:

- **Reviewer coverage is no longer missing.** Upstream added a 157-case frozen Reviewer development evaluator ([PR #165](https://github.com/X-McKay/corsair/pull/165)). This closes the missing-entry-point/set gap; a representative live/held-out baseline and independently qualified dispositions remain separate work. The final coverage table/evidence includes Reviewer; the original six-command baseline is retained as history.
- **Corrected D3 drafts are now checked again.** Upstream added up to three mechanical corrections per author/draft version, with diagnosis after each returned correction ([commit `8d90da31`](https://github.com/X-McKay/corsair/commit/8d90da31)). That source change addresses the original missing-recheck finding. The audit patch does not override the new correction budget or change disposition/probe semantics.
- **OpenShell is now implemented, not merely proposed.** [PR #169](https://github.com/X-McKay/corsair/pull/169) adds a sandbox port, explicit Docker/OpenShell selection, the official pinned OpenShell **0.1.3** SDK, native backend implementation, v2 policies and a restored runbook. Docker stays the default. [HANDOFF-0136](https://github.com/X-McKay/corsair/blob/06d4cbe21b891051811f80559a478881c061ee86/docs/development/handoffs/HANDOFF-0136-openshell-sandbox-backend.md) explicitly says no gateway run has qualified it. The relevant next task is to review/qualify the implemented adapter, not create a second backend or assume current 0.1.4 docs certify the 0.1.3 pin.
- **Evaluation telemetry improved upstream.** Run-record naming (`wall_s`, `tokens`, `retries`), per-agent parameter identity, status-unreported counts and null-preserving totals were added. The audit's task/evaluator completion coverage and policy-scope fixes are integrated alongside those fields; they do not restore the obsolete `latency_s` alias or discard upstream provenance.
- **Prompt rules evolved upstream.** Accepted D14–D17 and payload/PoV guidance were strengthened. The original CPU-only prompt ablation is historical development evidence at its recorded source identity, not a performance result for the newer instructions.

The remaining high-leverage priorities are **native Temporal retry/durability boundaries**, effective release/shared artifact provenance, cited and bounded negative review/counterfactual validation, mode-separated paired live evaluations and licensed native benchmark admission, plus evidence-based qualification of the actual OpenShell adapter. The initial audit sections below remain traceable source findings at the starting snapshot; this update prevents resolved gaps from being misreported as current.

## Most important confirmed findings at the starting snapshot

1. **P0 — Temporal mode does not implement the accepted per-model/per-tool PydanticAI durability design.** `SPEC-0082` requires native `TemporalDurability` for each model request and tool call, but [`workflow.py:1–26`](https://github.com/X-McKay/corsair/blob/bc3c25fa46686bdf3120b96caac174c39c8285af/src/corsair/v2/workflow.py#L1-L26) deliberately runs each entire agent episode as one Temporal activity. Static inspection found zero production `TemporalDurability` constructors and zero PydanticAI plugin registrations. A retry can therefore repeat earlier model/tool work in an agent episode, while provider errors converted into returned `StepResult`s do not trigger the declared model activity retry. This is a direct divergence from the accepted architecture, not an argument for a rewrite.

   **Architecture choice before further Temporal tuning:** either implement startup-registered, named PydanticAI durable agents and retain Corsair’s deterministic `compose`, Build, Execute, evidence, and verdict logic; or amend `SPEC-0082` to explicitly adopt stage-level durability, identify every side effect and its idempotency/uncertainty handling, and remove the unused native-durability surfaces. The first option is preferred while `SPEC-0082` remains authoritative. Do not adjust retry counts, streaming, or worker deployment semantics before choosing the retry boundary.

2. **P0 — Evaluation currently proves scripted plumbing, not model or native-workspace quality; its gates can falsely pass.** Builder “live” mode still uses `RecordedWorkspace`, so no command runs ([`agent_eval.py:125–138`](https://github.com/X-McKay/corsair/blob/bc3c25fa46686bdf3120b96caac174c39c8285af/evals/agent_eval.py#L125-L138), [`builder/evaluate.py:5–12`](https://github.com/X-McKay/corsair/blob/bc3c25fa46686bdf3120b96caac174c39c8285af/src/corsair/v2/agents/builder/evals/evaluate.py#L5-L12)). Reviewer has no frozen eval set or executable evaluator. More seriously, failed tasks have no assertion dimensions and are omitted from quality denominators, and an out-of-scope `applies_to.mode` policy can still return `pass` ([`agent_summary.py:68–82`](https://github.com/X-McKay/corsair/blob/bc3c25fa46686bdf3120b96caac174c39c8285af/evals/agent_summary.py#L68-L82), [`agent_summary.py:127–179`](https://github.com/X-McKay/corsair/blob/bc3c25fa46686bdf3120b96caac174c39c8285af/evals/agent_summary.py#L127-L179)). These can mislead policy assessment; current thresholds are deferred, so no production release approval is claimed. Correct accounting and truthful mode identity precede any accuracy, latency, token, or prompt-optimization claim.

3. **P0 — A corrected probe can bypass its required fresh trusted mechanical check.** After a D3 author correction, [`chain.py:631–653`](https://github.com/X-McKay/corsair/blob/bc3c25fa46686bdf3120b96caac174c39c8285af/src/corsair/v2/chain.py#L631-L653) freezes the changed draft and sends it to review without diagnosing the new bytes. Existing chain tests intentionally assert that the revision is *not* diagnosed. That contradicts the frozen/re-check/re-review rule in `SPEC-0082`. Add one silent diagnosis for every changed draft after the single permitted author correction; do not disclose another diagnosis or outcome to the author.

4. **P0 — Current developer instructions can direct an agent to a retired architecture and a nonexistent command.** Three general Claude/Codex-discoverable skills repeat a stale v1 role/migration rulebook, although the six current roles are Grounding, Investigator, Builder, Control Prober, Exploit Prober, and Reviewer. In addition, `make test-config` is instructed but absent from the Makefile. These defects undermine the golden path before a code change begins. The existing single-source symlink layout for `.agents/skills` → `.claude/skills` is sound and should be retained; repair only the stale body text and missing narrow target.

5. **P1 — Build/execution evidence and cleanup are incomplete on the existing Docker path.** The current Builder workspace drops the return value of `destroy()` ([`chain.py:203–210`](https://github.com/X-McKay/corsair/blob/bc3c25fa46686bdf3120b96caac174c39c8285af/src/corsair/v2/chain.py#L203-L210)), so a failed cleanup confirmation does not become `cleanup_unconfirmed` or a run-scoped reaper record. The requested `commands.jsonl` evidence is absent; current stage, message, usage, and replay-log artifacts do not constitute an immutable per-command receipt. These are small, high-leverage evidence fixes that should land before any OpenShell migration.

6. **P1 — Provenance is useful but does not yet bind an effective release, a worker version, an admitted image, or cross-worker artifacts.** `run.json` records commit, provider configuration and matrix inputs but omits selected Skills, capability/tool policy, lockfile and worker-image digests. `ArtifactStore` defaults to the process CWD and ignores `ArtifactRef.uri`, so a default store on worker B cannot read a reference written from worker A ([`artifacts.py:14–24`](https://github.com/X-McKay/corsair/blob/bc3c25fa46686bdf3120b96caac174c39c8285af/src/corsair/v2/artifacts.py#L14-L24), [`artifacts.py:46–50`](https://github.com/X-McKay/corsair/blob/bc3c25fa46686bdf3120b96caac174c39c8285af/src/corsair/v2/artifacts.py#L46-L50)). Plain Temporal workers also do not pin workflow task routing to a release-derived deployment version. Provenance recording must not be presented as deployment pinning.

7. **P1 — The Docker runtime is intentionally an interim implementation, with known admission and uncertainty gaps; OpenShell is not a present replacement.** A matrix declares package hosts but drops them during runtime construction; Builder/replay can use Docker bridge networking with no host allowlist enforcement. Local workload tags are only best-effort observed, not admitted immutable image digests. Intake hashes a tree once but later copies the mutable source path. A lost Docker exec stream is not typed separately from normal command completion. These are independent correctness/reproducibility issues. Docker remains the default until the specified v2 e2e/baseline gates pass; then a thin, explicitly selected OpenShell backend can be qualified row by row. Do not install a new scheduler, tracing system, or runtime rewrite to address them.

The rest of this report turns those findings into bounded changes, acceptance evidence, and an evaluation program. It distinguishes native facilities already used correctly from gaps that justify adoption.

## 1. Preserve the native foundations; remove only proven duplicate glue

Corsair is not broadly reimplementing PydanticAI/Harness. It already makes appropriate native use of `AgentSpec`/`Agent.from_spec`, typed output models, `UsageLimits`, `ModelRetry`, message-history serialization, Harness Skills, Harness `FileSystem`/read-only workspace access, `FunctionToolset`, `OpenAIChatModel`/`VLLMProvider`, and `WorkspaceBackend` conformance tests. Five agent factories construct agents from specifications, while keeping dynamic source roots, workspaces and typed dependencies in application code ([Investigator factory](https://github.com/X-McKay/corsair/blob/bc3c25fa46686bdf3120b96caac174c39c8285af/src/corsair/v2/agents/investigator/agent.py#L40-L76), [Builder factory](https://github.com/X-McKay/corsair/blob/bc3c25fa46686bdf3120b96caac174c39c8285af/src/corsair/v2/agents/builder/agent.py#L38-L63), [Prober factory](https://github.com/X-McKay/corsair/blob/bc3c25fa46686bdf3120b96caac174c39c8285af/src/corsair/v2/agents/probing/agent.py#L56-L78), [Reviewer factory](https://github.com/X-McKay/corsair/blob/bc3c25fa46686bdf3120b96caac174c39c8285af/src/corsair/v2/agents/reviewer/agent.py#L21-L46)). This division is aligned with the native specification and capability model. [1] [2]

Retain Corsair-owned seams where they enforce product semantics that vendor primitives do not supply:

- Keep the assigned-path `write_test_file`/`finalize_draft` controls, frozen-draft reconstruction from native history, marker/token protocol, and one-file rule. A generic writable filesystem capability is not equivalent.
- Keep code-computed Reviewer validity and resolved citation checks. Native structured output validates shape and retries; it cannot establish outcome blindness, frozen-byte binding, or verdict semantics.
- Keep the Builder argv-only command boundary, output/time bounds, recipe/replay contract, exact input-tree binding, and evidence artifacts. Harness Shell has useful ergonomics but is not a Corsair domain/evidence replacement.
- Keep the aggregate Corsair usage budget across correction loops and the read-loop guard. Independent native retry layers can multiply calls; the existing aggregate policy is therefore not redundant. [3]
- Keep `DockerWorkspace` until a separately qualified `OpenShellWorkspace` replaces its mechanics. PydanticAI’s workspace protocol defines lifecycle/conformance, not containment or a Docker implementation. [4]
- Keep `prompted_output.py` until the actual endpoint/model profile passes a native structured-output and strict-tool canary. The current VLLM-compatible profile deliberately disables JSON-schema/object output and strict tools ([`models.py:109–127`](https://github.com/X-McKay/corsair/blob/bc3c25fa46686bdf3120b96caac174c39c8285af/src/corsair/v2/models.py#L109-L127)); a generic provider’s advertised model-family defaults are not evidence about Corsair’s endpoint. [5]

The immediate code-deletion candidate is narrow. Migrate Investigator’s inline `guidance_block()` and Builder’s absent framework guidance to the same selected, on-demand Harness Skill pattern already used by authors and Reviewer; once role-isolated tests prove the selected skill loads correctly, delete only `agents/common/framework.py` and its direct-injection tests. `ToolOutputLimits` is also a qualified candidate for source-read results, but not a drop-in for Builder output clipping: it may retain model-visible data in the workspace. Prototype deterministic truncation for `read_file`/`search_files` before changing persistent output or source-size behavior. [2] [6]

### 1.1 Required P0/P1 contract repairs in prompts, validators, and chain sequencing

**D3 correction re-check (P0).** Change only the correction path in `compose`/`check`:

- Freeze the returned control/exploit pair and calculate a new immutable digest.
- For each changed draft, run `diagnose` once against that frozen byte sequence.
- Record the result for the run; do not pass its text or a second correction entitlement to the author.
- Review and Execute only the checked corrected digest. If the trusted check cannot be completed, follow the existing inconclusive/not-run semantics rather than allowing unbound bytes onward.

Acceptance is a deterministic fake-chain test—not a model evaluation. Start with initial control/exploit diagnoses, make one author correction, require diagnosis of the corrected control (and corresponding exploit when changed), and assert final review/execute receive the corrected digest. Repeat for a review-revision correction. Assert no second author call and no execution/diagnosis-output leakage into author input.

**Reviewer evidence and output bounds (P1).** [`review.py:93–116`](https://github.com/X-McKay/corsair/blob/bc3c25fa46686bdf3120b96caac174c39c8285af/src/corsair/v2/agents/reviewer/review.py#L93-L116) requires citations only for wholly positive checks; an invalid result can currently carry a defect and no citations. Move the feedback envelope into the Pydantic model: at most four defect strings, each at most 1,024 characters, plus bounded citations. Require at least one resolved frozen-test citation and one production-source citation for both positive and negative judgments. Continue to compute `valid = all(checks)` in code, and continue to filter the peer-test citation before author feedback. Acceptance cases must reject uncited negative review, reject five defects and a 1,025-character defect before feedback, accept a cited negative review, and prove peer-citation filtering.

**Exploit counterfactual (P1).** `ProbeBrief.safe_observation` defaults to an empty string and `plan_problems()` does not require it for planned exploit work ([`contracts.py:162–176`](https://github.com/X-McKay/corsair/blob/bc3c25fa46686bdf3120b96caac174c39c8285af/src/corsair/v2/contracts.py#L162-L176), [`validation.py:50–75`](https://github.com/X-McKay/corsair/blob/bc3c25fa46686bdf3120b96caac174c39c8285af/src/corsair/v2/agents/investigator/validation.py#L50-L75)). Add a role-conditional validator requiring nonblank `safe_observation` for a planned exploit brief. Keep semantic non-vacuity in Reviewer: a populated but content-free sentence is not proof of a counterfactual. Acceptance: missing only `safe_observation` yields `ModelRetry`; a weak but populated field remains schema-valid and is caught by a Reviewer fixture.

**Skill/procedure compactness (P1/P2).** First prompts should carry a short role constraint and selected-skill catalog, not full framework prose. The agent must load mandatory protocol/role/framework Skills before source work; manifests remain the concise non-negotiable authority. This reduces duplicated maintenance and initial context without asserting a token or accuracy saving. Static ceilings are currently high: 20,000-character source tool responses with up to 30 calls, and Reviewer can inline two 64-KiB drafts before reading source. These are ceilings, not measurements. The first acceptance is a native-skill host test: initial request excludes framework body; `load_capability("pytest")` exposes the known marker template; paged reads retain citations after deterministic head/tail truncation. Do not reduce the 64-KiB draft contract until data show an admitted case needs less.

**Marker-interface decision (P2, blocking prompt-only changes).** `SPEC-0082` describes separate start/check/end environment paths, while all current executor, protocol skills and canaries use `CORSAIR_MARKER_DIR` plus `CORSAIR_TOKEN` ([`execute.py:30–34`](https://github.com/X-McKay/corsair/blob/bc3c25fa46686bdf3120b96caac174c39c8285af/src/corsair/v2/execute.py#L30-L34), [`probe protocol`](https://github.com/X-McKay/corsair/blob/bc3c25fa46686bdf3120b96caac174c39c8285af/src/corsair/v2/agents/probing/skills/probe-protocol/SKILL.md#L17-L46)). Obtain a design-author decision, then amend the accepted record or atomically migrate trusted executor, contracts, skills and canaries. A prompt-only correction risks reclassifying all probes as anomalous/not-run.

## 2. Make durability and records truthful, then use Temporal’s native controls

### 2.1 Preferred native Temporal implementation, without changing domain architecture

The accepted architecture can be met with a bounded replacement of the **whole-agent activity wrapper**, not a rewrite of `compose`.

- At worker startup, construct stable named agents and stable toolset IDs from the locked release. Attach `TemporalDurability` before the worker starts; use the documented PydanticAI registration/plugin path verified against the locked 2.55.0 package, not docs-head assumptions. Native durability routes model requests and wrapped tools into activities while the agent loop is durable. [7]
- Keep `compose()` as deterministic domain sequencing: plan ownership, correction cap, outcome blindness, trusted checks, budget aggregation, artifact references and verdict rules stay Corsair-owned.
- Keep Build, replay, Diagnose and Execute as trusted domain activities. Builder shell commands and probe execution must remain logical-once/uncertain-on-failure, not become “retry model tools.”
- Replace the custom per-stage `MODEL_RETRY` wrapper only after a test-server parity and retry-ledger suite passes. Do not duplicate a scheduler or implement a distributed lock.

The decisive test-server acceptance uses a deterministic `FunctionModel` and one function tool, with the exact locked dependencies. It must prove registered separate model/tool activities, stable activity names after worker restart, replay to the same typed `Verdict`, direct-versus-Temporal typed-output equivalence, and one Builder effect after an injected post-effect error. This is an integration test, not an accuracy claim.

**Alternative if the team chooses stage-level activities:** amend `SPEC-0082`, README and active plans before retaining it. Remove optional durability factory parameters/imports and construction-only tests that imply a production feature. The amendment must list every tool/side effect that a stage retry can replay and define its idempotency key, error classification and uncertain-delivery behavior. This option gives up per-operation native durability; it must not retain its name in documentation.

### 2.2 Cancellation, artifacts, release routing, retry, and capacity

**Cancellation receipt and activity lifecycle (P1).** Existing activities specify only `start_to_close`, have no heartbeats, and call record finish only after normal composition return ([`workflow.py:195–257`](https://github.com/X-McKay/corsair/blob/bc3c25fa46686bdf3120b96caac174c39c8285af/src/corsair/v2/workflow.py#L195-L257)). Long work can therefore remain open without a terminal receipt. Native durable PydanticAI agents provide the preferred model/tool heartbeat path; retained blocking Docker work needs a small activity-local heartbeat/cancellation wrapper around the worker-thread wait. On cancellation: clean up labelled resources, write a distinct cancellation receipt, preserve last-step evidence, re-raise cancellation, and never fabricate a Verdict. Temporal requires a heartbeat timeout as well as heartbeats for cancellation delivery to a non-local activity. [8] [9]

The direct path has the same evidence defect: a deterministic `CancelledError` reproduction left `finished_at: null` and no summary/verdict/timings. Add additive lifecycle receipt fields for recorded, completed and cancelled calls, plus `stopped_at`; a persisted receipt must not imply that a process is still running. Catch/re-raise direct `CancelledError` only to persist `cancelled`, safe exception class/detail and last started stage; keep `finished_at` null when no Verdict exists. A local record after process loss is **incomplete**, not evidence that work is active. Acceptance must prove cancellation propagation, absent Verdict/summary, null `finished_at`, and compatibility of completed fixtures. Durable cancellation needs a separate test-server then non-production qualification.

**Shared artifact resolver (P1).** Inject one run-shared, content-addressed root/object-store configuration into `WorkerConfig`/`LocalOps`; pass it explicitly to Build/Execute/replay. Retrieval must resolve only allowed locations, verify digest **and size**, and use a documented immutable retention policy. A two-root unit case should fail before this change; then a two-worker Temporal test-server scenario must prove a Build artifact written by worker A resolves by `ArtifactRef` on worker B. Temporal External Storage is a separate history-payload facility, currently public preview; it does not replace Corsair evidence identity or retention. [10]

**Release tuple and worker versioning (P1).** Create an `effective_agent_release` manifest at agent construction and persist its digest plus material inputs in `run.json`:

- selected `agent.yaml` paths/digests;
- selected role/protocol/framework `SKILL.md` paths/digests, excluding unselected skills;
- capability/tool-policy digest or source package digest;
- lockfile and PydanticAI/Harness version identity;
- provider-profile/compatibility profile identifier;
- worker image digest, admitted workload image digest, matrix/runtime digest; and
- operator budget/profile inputs needed to interpret behavior.

Do not mix untrusted revision-tree bytes into the agent release; preserve case/revision evidence separately. A mutation test must show that altering a selected skill changes the effective release and run record, while altering an unselected framework skill does not until selected. Then configure Temporal Worker Versioning with a release-derived build ID and pinned workflow behavior; retain old workers until drain. The locked Temporal SDK is not obviously too old for that capability, but deployment behavior requires non-production proof. [11] Replay frozen historical histories in CI and prove an in-flight build-A run remains on A across an incompatible build-B deployment while a new run routes to B. Recording a digest without this routing test remains provenance, not pinning.

**Retry ledger and uncertainty (P2).** Define one written ledger after the architecture choice:

- model/read operations: bounded retry, exact maximum, nonretryable permanent validation/input errors;
- idempotent source reads: bounded retry only if safe;
- Builder/probe commands: one logical submission, an operation ID/idempotency key, no blind repeat after a post-start exception;
- unknown/possibly-completed remote command: `infra_error`/uncertain, partial-output artifact if available, no automatic re-launch;
- provider/transport retries: disabled or explicitly included in the same stated budget; and
- workflow: no blanket retry policy.

Temporal activities are at-least-once by nature, so “once” means a single logical effect with an idempotency/uncertainty contract, not a guarantee after acknowledgement loss. [12] Acceptance doubles must capture `(workflow_run_id, activity_id, idempotency_key)` and exercise transient model error, permanent error, post-effect failure and uncertain completion. Worker crash/acknowledgement loss remains live Temporal qualification.

**Capacity statement (P2).** `max_concurrent_activities=1` limits each model Worker process, not all workers on a queue ([`workflow.py:270–285`](https://github.com/X-McKay/corsair/blob/bc3c25fa46686bdf3120b96caac174c39c8285af/src/corsair/v2/workflow.py#L270-L285)). Correct the comment/operational claim. If global serialization is policy, enforce one model-worker replica through deployment configuration; otherwise set and report explicit per-worker and fleet capacity. Do not create a distributed semaphore. A two-worker concurrency double must reveal the present high-water mark, followed by non-production Docker/provider load qualification for selected replica and workspace slot counts. Native worker concurrency settings are per-worker tuning controls. [13]

## 3. Repair the Docker evidence path now; defer OpenShell under explicit gates

The immediate objective is a more reproducible **Docker** path, not a premature switch in runtime. Docker already enforces no network during probe execution and uses several useful hardening flags, but current source neither proves general isolation nor enforces matrix host policies. Treat every claim below as a correction to evidence/admission, not a generic security program.

1. **Structured command receipts and cleanup.** Write one append-only, redacted `commands.jsonl` receipt for every Builder, replay, Diagnose and Execute command. It should include run/workspace identity, command/request ID, argv hash plus safe/redacted argv representation, start/end, timeout, output artifact digest/size, exit or exception classification, and delivery state (`confirmed`, `uncertain`, `not_started`). Do not store secrets, raw tool contents, or substitute console logs for receipts. Surface a false `backend.destroy()` result as `cleanup_unconfirmed` and create a run-scoped reconciliation/reaper record. Acceptance injects a failed destroy and expects R1 `cleanup_unconfirmed`; simulates a stream loss after remote start; and proves no second command launch.

2. **Image admission.** Add an operator-owned workload-image lock. Before model or probe work, resolve the runtime image and require equality with the admitted immutable digest; a missing inspection or a tag retarget must refuse the run. Record admitted and observed workload identity separately, including future OpenShell component digests. The source currently loses `base_image`/`image_source` in `Row.runtime()` and returns `None` on Docker inspection failure ([`matrix.py:35–60`](https://github.com/X-McKay/corsair/blob/bc3c25fa46686bdf3120b96caac174c39c8285af/src/corsair/v2/matrix.py#L35-L60), [`docker.py:93–103`](https://github.com/X-McKay/corsair/blob/bc3c25fa46686bdf3120b96caac174c39c8285af/src/corsair/v2/workspace/docker.py#L93-L103)). This is a reproducibility control; it is not a claim that a digest alone validates a workload.

3. **Source identity.** Snapshot source as a content-addressed artifact, or rehash immediately before the Build copy and refuse a mismatch. Current Intake’s initial digest does not bind bytes copied later from the mutable path ([`intake.py:32–61`](https://github.com/X-McKay/corsair/blob/bc3c25fa46686bdf3120b96caac174c39c8285af/src/corsair/v2/intake.py#L32-L61), [`build.py:53–70`](https://github.com/X-McKay/corsair/blob/bc3c25fa46686bdf3120b96caac174c39c8285af/src/corsair/v2/build.py#L53-L70)). Test create-case → mutate-source → replay; it must fail before baseline and not populate a cache keyed by stale tree hash. Git commit-to-tree/remote validation is a separate, explicit provenance choice.

4. **Network policy truthfulness.** Preserve the current no-network execution phase. Do not claim a Docker bridge is narrowed merely because `build_network_hosts` appears in a matrix: [`Row.runtime()` drops it](https://github.com/X-McKay/corsair/blob/bc3c25fa46686bdf3120b96caac174c39c8285af/src/corsair/v2/matrix.py#L35-L60), while Builder/replay can use bridge networking. Record this as a Docker limitation and do not expose a policy-mutation/proposal tool to agents.

### 3.1 OpenShell: future native adapter, not a substitute for Corsair domain logic

NVIDIA OpenShell is the relevant sandbox runtime: gateway, trusted supervisor, and workload-side runtime; it is distinct from PydanticAI’s workspace protocol. It can provide policy-mediated network/process/filesystem controls, typed request outcomes, and lifecycle APIs, but its platform logs are temporary/supplemental and do not prove Corsair marker, revision, test, or verdict semantics. [14] [15] [16]

`SPEC-0082` already defers OpenShell/kind until decisive e2e runs in three languages and a promoted baseline for every agent. Keep that gate. When it opens:

- Pin one explicit OpenShell release, matching Python SDK/CLI/gateway/supervisor/sandbox-runtime/policy tuple, Docker driver and workload image digests. Do not use `latest` or an unversioned documentation path; the audited documentation channels showed a 0.1.3/0.1.4 inconsistency. [17]
- Qualify the Docker driver first with the existing rows. Test readiness/admission, upload/download hashes, command success, stream loss, resource control, declared-host allow/deny, file/process denial, policy digest/log export, deletion wait and original-identity cleanup. OpenShell network policy should compile only an operator-owned matrix allowlist; it should deny undeclared, public/private/link-local destinations with attributed policy evidence. [18]
- Add a thin `OpenShellWorkspace(WorkspaceBackend, SupportsCommands)` under an explicit operator backend selection. No automatic Docker fallback after OpenShell admission or execution failure. Map `REQUEST_OUTCOME_UNCERTAIN` and `REQUEST_STREAM_UNAVAILABLE` to the existing uncertain-infrastructure terminal path and receipts. [19]
- Move to kind/Kubernetes only after a separately admitted driver/CNI gate. Native sandbox platform/kernel admission must pass; Docker-driver success does not prove Kubernetes behavior. [17]

Delete Docker-specific create/exec/copy/network helper implementation only after each admitted row has equivalent OpenShell conformance, command receipts, cleanup evidence, canary/replay/probe/e2e comparisons and a measured decision. Retain Corsair-owned source binding, matrix/image/policy admission, frozen patches, differential outcome rules, blind review, evidence redaction, command receipt schema and terminal reasons.

## 4. Evaluation must be mode-separated, failure-complete, grouped, and paired

### 4.1 Correct the evaluation contract before collecting a baseline

Make the following small changes before scheduling any provider calls:

- Rename the current Builder provider-enabled fixture route **`live-model-fixture`**. It is a legitimate deterministic model-behavior cohort but must never be displayed as native Docker or live workspace. Add **`live-workspace`** only when a disposable Docker workspace executes the expected baseline/probe with real command receipts. Preserve **`scripted`** for no-model oracle replay and distinguish chain `e2e` evidence explicitly.
- Add `attempted`, `completed`, `provider_error`, `evaluator_error`, `workspace_error`, and `qualification_coverage` alongside semantic dimensions. Quality may continue to report completed cases as its denominator, but release promotion must gate completion/failure coverage separately. The required regression is one correct completion plus one failure: quality `1/1`, completion `1/2`, and a strict completion threshold fails.
- Return `not_applicable` before threshold evaluation when manifest/set/mode does not match `applies_to`. An out-of-scope scripted result cannot serialize as a live policy pass.
- Version/document quantile semantics, supply p50 **and p95** (p90 only if intentionally retained), and test fixed values 1–10. Do not attach an uncertainty claim until minimum sample/repeat policy exists.
- Create frozen Reviewer cases and a nonempty grouped holdout **before** prompt/tool tuning. Group by repository/family/tree/near-duplicate diff; vulnerable and fixed variants, copied scenarios and counterpart trees must never cross development/holdout. Current all-`held_out: false` manifests and known duplicated inputs establish that frozen files alone do not establish generalization.
- Add explicit execution provenance to each row: mode, provider/model/profile, workspace backend, runtime/image digest, source/revision hash, effective-agent-release digest, case/manifest hash and a null-preserving usage receipt.

Pydantic Evals offers Dataset/Case/report foundations and optional native trajectory/span evaluators; the latter require locally configured OTel/Logfire-compatible spans and are not evidence today. [20] [21] [22] Keep Corsair deterministic marker, frozen-patch, differential outcome and blindness evaluators authoritative; use native `ToolCorrectness`, `TrajectoryMatch`, argument, maximum-tool-call/request and matching-span evaluators only after local trace retention is explicitly approved and content-safe spans exist.

### 4.2 Concrete experiment matrix — execute as separate cohorts, not a pooled headline

Each cohort below is a proposed experiment. It is **pending parent scheduling, credentials, Docker/Temporal availability and baseline execution**. Every published row must state the mode and attempted/completed/qualified counts; null provider usage stays null.

- **Configuration control, all five current languages (Python, Java, JavaScript, Ruby, Perl):** run the current frozen development set in scripted mode once to preserve plumbing/regression identity. Measure evaluator completion and deterministic contract results only. Do not report it as accuracy, latency or tokens.

- **Reviewer closure, all five current languages where applicable:** create a small frozen development set with copied/mocked targets, harmless input, real target binding, vacuous assertion, marker/token mismatch, broad catch, uncited negative review, peer-citation leak and the guarded Test::More end-marker exception. First run scripted; then, only in an approved provider cohort, run three fresh repeats per case. Report reviewer criterion confusion matrix, citation-validation retries, tool/read counts, prompt/input/output tokens when supplied, wall time and completion. The evaluator alone retains expected flags.

- **Live-model-fixture agent contract cohort:** for Investigator, Builder, Control Prober, Exploit Prober and Reviewer, run the exact same frozen inputs against one approved profile, then the candidate profile/prompt/skill change. Builder remains fixture-labelled. Pair by case and repetition, freeze model profile, effective release, usage limits and evaluator. Capture structured-output retries, tool trajectory, input/output tokens, wall time and error class. This isolates model/prompt compatibility from native execution.

- **Live-workspace builder/prober cohort:** select a small, disposable, admitted Docker set in every supported language. A run must record resolved workload image, source snapshot, command receipts, baseline outcome and qualification result. Run control and exploit probes against the two frozen revisions three times in fresh workspaces. Report separate build success, control pass, vulnerable exploit pass, fixed exploit fail, cleanup confirmation and uncertainty outcomes; do not collapse inability to build into semantic safety.

- **Direct-versus-Temporal parity cohort:** with deterministic function models first, then an approved provider only after native durability is implemented, run the same typed cases in direct and Temporal modes. Compare output schema, allowed/refused tool boundaries, frozen digests, classification, retry counts, terminal receipts and trace/receipt sequence. Do not require byte-identical model text or command strings. A mismatch is a durability regression, not a model-quality statistic.

- **Prompt/skill compactness cohort:** baseline current role prompt against selected Harness Skills plus shortened manifest, one role at a time. Hold source, provider/model/profile, tool limits, case list and repeat/order fixed. Promote only if the candidate meets the predefined noninferiority completion and correctness bounds on development data, does not increase unsafe/invalid trajectories, and does not degrade a locked holdout. Token/cost/latency reduction is measured per paired completed attempt; it is never inferred from character counts.

- **Tool-output bounds cohort:** baseline 20,000-character source results against a deterministic `ToolOutputLimits` head/tail prototype (for example, 8,000 characters) using cases where the needed cite is at the head and tail. Record citation validity, extra read pages, read-loop guard interventions, total returned characters, token use and latency. Reject the bound if it causes required source evidence loss or more completion failures; do not spill to a writable workspace by default.

- **Provider compatibility cohort:** retain prompted structured output as control. Against a specifically authorized non-production endpoint, run two native JSON-schema/strict-tool canaries containing nested schema, tool call, output retry and thinking on/off with the exact Corsair request shape. Promote a per-endpoint compatibility profile only if both runs preserve typed output/tool boundary and provider usage receipts. Otherwise retain conservative prompted mode. Docs are not qualification. [5]

- **Temporal/Docker operational cohort:** after test-server checks, use non-production workers, shared artifacts and controlled failure injection. Measure cancellation latency/cleanup receipt, cross-worker artifact retrieval, replay, worker-version routing, per-worker/fleet concurrency high-water mark, command uncertainty and size rejection. These are operational results, not agent accuracy measurements.

- **Future OpenShell parity cohort:** only after `SPEC-0082` gates, repeat the admitted Docker workload cohort on one explicit OpenShell Docker-driver tuple. Compare native command/evidence classification, control/probe outcomes, cleanup, policy events, resource use and wall time on paired source/image cases. No isolation/performance claim may be generalized to kind/Kubernetes or other versions.

### 4.3 Metrics and reporting rules

For every **qualified issue pair**, report by language, corpus/family/project, CWE, runtime row, model/profile, mode and revision. Never pool repeated or vulnerable/fixed pair observations as independent samples.

- **Disposition:** report sensitivity and specificity with abstentions in denominators as specified, false approval (`LIKELY_NOT_EXPLOITABLE` on qualified reproducing positive), false rejection, decisive rate, each abstention/terminal reason, attempted/completed and qualification coverage. A source label, a fix commit, or a model refusal is not a qualified negative.
- **Fix verification:** report `verified`, `not_verified` and `not_applicable` independently. “Verified” means the frozen control passes on both revisions, exploit passes vulnerable and fails fixed, and reviews are positive—not merely that a fixed counterpart exists.
- **Cost and latency:** report per completed attempt input/output/total tokens, model requests, tool calls, retries, run wall time and agent-call wall time (clearly noting summed agent time may exceed elapsed wall time). Report p50/p95 only with documented quantile/sample policy and observed sample count. Unknown usage stays null; do not impute zero or fabricate cost.
- **Uncertainty:** provide raw `n`, denominators and 95% Wilson/bootstrap intervals for rates. Use paired bootstrap intervals (or another predeclared paired method) for same-case candidate/baseline deltas. Cluster interpretation by family/repository. Three fresh workspaces per live case is a minimum initial repeat, not a basis for a broad significance claim.
- **Trajectories:** retain required/forbidden local tool calls, argument subsets, ordering, cap adherence, post-halt prohibition, outcome-blind boundary and direct/Temporal equivalence. Native content-safe spans may provide structural model/tool timings; they do not supersede domain checkers.
- **Release policy:** predeclare thresholds using development/validation live results, then confirm them on an untouched held-out cohort without retuning. First optimize false approvals, then abstention/completion, then cost/latency, matching the architecture’s stated safety ordering. A performance aggregate must identify the exact effective release and telemetry coverage beside every delta.

### 4.4 Dataset admission and mapping

Use the evidence hierarchy **qualified native pair > reproducible PoV pair > source/fix metadata > source label**. Every imported datum needs source URL, licence/reuse status, immutable commit/artifact digest, language, family/group, revisions, oracle qualification status and whether it is development or holdout. Do not bulk-import a corpus before a small, repeatable admission sample succeeds.

- **Current vendored InfoSec Harness:** retain as a controlled synthetic regression corpus with its imported commit/tree digest. It has 82 fixtures (Python 42, Java 6, JavaScript 18, Perl 12, C 4), but its copied tree has `NOASSERTION` licensing status, `HEAD` rather than historical revisions, and no Java verification. It is appropriate for scripted/contract regressions and canary protocol coverage, not a production-scale or independently held-out benchmark. Resolve reuse authorization before redistribution and run Java verification before treating Java labels as disposition truth.

- **Java:** begin external native admission with **Vul4J** PoV entries, not its SpotBugs-only rows. It provides CC-BY-4.0 data and Java PoV/human-patch material, but each entry still needs the Corsair control/PoV pair on a pinned image. Use **NIST Juliet Java 1.3** for large synthetic marker/protocol/mutation canaries and **OWASP Benchmark** for runnable Java positive/negative calibration; neither substitutes for historical two-revision fix verification. [23] [24] [25]

- **JavaScript/TypeScript:** use **OpenSSF CVE Benchmark** as an MIT-licensed discovery/split source with vulnerable/patched SAST-oriented CVEs. Recover/admit a native two-probe oracle before chain scoring; its vulnerable/patched code alone is not a universal exploit oracle. Supplement with carefully admitted, pinned **CVEfixes** candidates where a reproducible test can be established. [26] [27]

- **Python, Ruby and Perl:** preserve the present synthetic controlled set for cross-language protocol parity. Use a pinned **CVEfixes** SQL snapshot only as licensed discovery/metadata to identify candidates; it has broad before/after source but not a per-row native test oracle. Qualify pairs individually in their runtime rows. Until a licensed executable pair corpus is admitted, report these language slices as controlled-corpus/live-workspace coverage, not broad real-world benchmark accuracy. [27]

- **C/C++:** use **NIST Juliet C/C++** for deterministic synthetic good/bad program and mutation canaries; explore **PrimeVul** only as a function-level calibration/discovery seed after recording the Google Drive artifact digest and commit revisions. **Big-Vul/MSR-20** and **DiverseVul** are metadata/localization candidates, not execution truth: Big-Vul’s changed lines and DiverseVul’s missing/reuse constraints cannot establish reproduced disposition. [24] [28] [29] [30]

Keep imported vendor README content byte-for-byte when required; document a waiver rather than silently editing third-party material. The data admission report should include rejection reasons (licence unresolved, missing revision, no runnable control/PoV, incompatible image), so benchmark coverage is not improved merely by dropping difficult cases.

## 5. Performance trade-off decisions must be evidence-gated

Apply these decision rules to prevent plausible optimizations from reducing correctness or reproducibility:

- **Prompt/skill compaction:** adopt only after isolated, paired development noninferiority and untouched holdout validation. If completion, reviewer citation quality, trusted-check success or trajectory adherence decreases, retain the longer version even if tokens fall. Character counts are not token/cost measurements.
- **Read/draft caps:** first cap native tool output deterministically, preserving tail/head citation access and pageability. Reject a cap when it hides required source evidence or increases repeat reads/retries enough to erase the token/latency benefit. Never substitute a model summary for frozen draft bytes.
- **Native structured output/strict tools:** default remains prompted output. A profile promotes only after two approved endpoint canaries show identical typed boundaries under the real nested-schema/tool/retry request. Compatibility is profile-identity data, not a global switch.
- **Caching:** do not enable by default. Promote `Caching(messages=False)` only if an endpoint reports cache read/write token fields in a bounded two-turn test, paired measurements show benefit on long immutable instructions, and cache retention is acceptable. Prompt caching never replaces Corsair recipe/environment/evidence cache keys. [31]
- **Streaming:** add only for a concrete operator/UI requirement. Require ordered redacted event/terminal-result tests, payload-size/retention rules and terminal behavior after interruption. Do not route source/test/model content through progress events. Native durable streams can be buffered and constrained by Temporal payload limits. [7]
- **Concurrency:** choose a declared fleet policy, then qualify it under load. If global one-model-at-a-time is required, enforce one worker replica; otherwise optimize through native worker replica/slot settings and report fleet capacity. Never use a custom distributed scheduler solely to preserve an unsupported comment.
- **Temporal versus stage activity:** choose native per-operation durability for correctness and cancellation/retry attribution if the specification stays; choose stage activities only with explicit accepted trade-offs. Benchmark wall time only after equivalent cases, models, profile, workers, retry ledger and artifact store are in place.
- **Docker versus OpenShell:** retain Docker as default until comparable, admitted row-by-row results exist. Adopt OpenShell for observed policy/stream/lifecycle evidence, not presumed accuracy or performance. A Docker-driver result does not transfer to kind/Kubernetes.
- **OTel:** standardize only if an operator supports a local/export destination and retention policy. Use native `Instrumentation` across all six factories with `include_content=False`, binary content off and model-request parameters off. Keep `RunRecorder` as the authoritative evidence record. An in-memory tracer test must prove agent/model/tool spans and absence of raw prompt/source/tool content; `usage.json` must continue with tracing absent. [32] [33]

## 6. Polished CLI and Claude/Codex golden paths

### CLI: fix factual states before terminal polish

Two deterministic user-facing defects deserve the first CLI patch:

- `run_case()` starts a record but a direct cancellation leaves no persisted cancellation state; do not call it a completed error or resumable workflow ([`chain.py:672–686`](https://github.com/X-McKay/corsair/blob/bc3c25fa46686bdf3120b96caac174c39c8285af/src/corsair/v2/chain.py#L672-L686)).
- `corsair-v2 runs compare` accepts a nonexistent directory, prints dashes, and exits zero because missing JSON is converted to `{}` ([`runs.py:24–53`](https://github.com/X-McKay/corsair/blob/bc3c25fa46686bdf3120b96caac174c39c8285af/src/corsair/v2/runs.py#L24-L53)). Missing/unreadable/malformed root records must be a stderr diagnostic and nonzero result; a valid unfinished record must display `incomplete`.

Keep `argparse`; add a direct pinned Rich 15.0.0 dependency, a thin reporter interface, and only `--format text|json` plus `--color auto|never`. In JSON mode stdout contains **exactly one** versioned JSON object; progress and diagnostics use stderr. In non-TTY text mode, emit non-animated structural stage lines to stderr. In TTY text mode, one indeterminate Rich spinner and stable labels are sufficient. Honor `NO_COLOR`; never encode state only by color. Add a start event before code stages, but do not display invented percentage progress or infer remote Temporal state from a local record. Rich supports this terminal/pipeline behavior without a parser migration or a Textual application. [34] [35]

Show existing per-agent aggregates after completion: agent, steps, calls, request count, input/output/total tokens, tool calls, summed agent seconds and statuses; retain explicit unknown/nulls. Later, if native event streams are qualified, record redacted structural tool start/end receipts only—tool identity, event type, monotonic time/duration—not arguments, results, source or model text. The final native `RunUsage` remains authoritative. This patch excludes resume, remote cancellation/status, doctor network probes, OTel export, custom trace parsing and p95 calculation.

CLI acceptance fixtures: direct cancellation state with no Verdict; nonexistent/malformed/complete/incomplete run directories; one parseable no-ANSI JSON stdout value; no animation in a pipe; `NO_COLOR`; code-stage `started` then exactly one terminal event; null-preserving aggregate display; and one-tool structural receipt only when the later event path is adopted.

### Claude/Codex and local developer golden path

The existing five skill symlinks and front matter are already a strong cross-client foundation. Claude discovers `.claude/skills`; Codex can discover `.agents/skills` symlinks, so do **not** duplicate skill bodies or add optional Codex metadata merely for symmetry. [36] [37]

The repair is content and command correctness:

1. Review skill edits against current Claude/Codex discovery conventions. Remove only the copied v1 six-role/migration blocks in `corsair-development`, `corsair-review` and `corsair-handoff`; point current architectural facts to `SPEC-0082`/`AGENTS.md`. Preserve task-specific procedures and historical handoffs as snapshots.
2. Add `make test-config` as the narrow locked configuration suite, preferably `uv run --locked python -m pytest $(PYTEST_ROOT) tests/configuration`. Confirm `make test-v2` still contains it. Add a small guard that generic skills contain no retired role list/record IDs and `.agents` links resolve.
3. Reconcile stale `PLAN-0097` against implemented code, scripted evidence, image/Docker-only evidence, inference and live qualification. Keep unrun/deferred gates explicitly unchecked. Do not rewrite historical handoffs to make the plan look complete.
4. After the Reviewer set exists, the practical offline path is `make test-config`, `TEST_WORKERS=0 make test-v2`, `TEST_WORKERS=2 make test-v2`, then `make eval AGENT=reviewer SET=development`. The latter is scripted until an approved provider run occurs.
5. Add a small pinned `check` path only after configuration/dependency adoption: `uv run --locked ruff format --check .`, `uv run --locked ruff check .`, and a scoped `uv run --locked ty check src/corsair/v2`. Fix the CI worker count (for example 2) while retaining `auto` locally; serial and fixed-parallel must yield identical pass/fail/skip sets. [38] [39]
6. Repair authored relative Markdown links to current/immutable targets. Preserve imported vendor documents byte-for-byte and document any intentional inherited broken link.

The existing `providers.local.json` is actually a remote HTTPS profile. Normal local llama.cpp configuration requires an explicit development-provider design, rather than a silent production-policy bypass: current rules allow inference only at `llm.almckay.io`, model validation rejects HTTP, and the factory hard-codes `VLLMProvider`. The current user expressly requested a separate local experiment, which does not amend normal provider configuration. For a supported developer-only loopback profile, document its scope first; then add one explicit loopback-only OpenAI-compatible native profile, reject non-loopback HTTP, rename/document the remote sample, and qualify one pinned fixture request. Do not create a llama-specific adapter or call this agent-quality, Docker, or production qualification. [5] [40]

## 7. Concise phased backlog with bounded components and dependencies

- **Phase 0 — Stop false guidance and false passes (small, offline; P0).**
  - Components: `Makefile`, three generic skill bodies, skill/link guard, `agent_summary`, release-policy scope handling, quantile schema/tests.
  - Deliverables: working `make test-config`; no stale v1 roles in generic skills; wrong mode/set is `not_applicable`; failures visible in completion coverage; p95 implemented/documented.
  - Dependencies: none beyond locked test environment; skill edits preserve shared-source/discovery conventions.
  - Acceptance: targeted unit/configuration tests plus serial/fixed-parallel suite are parent validation tasks. No provider/Docker result is implied.

- **Phase 1 — Restore chain and record truth (small/medium; P0/P1).**
  - Components: D3 re-check sequence/tests; Reviewer bounds/citations; exploit `safe_observation`; direct cancellation lifecycle fields; compare input validation; minimal Rich reporter/JSON output; selected-skill effective-release manifest mutation test.
  - Deliverables: corrected-draft check evidence; citation-bearing review evidence; honest `cancelled`/`incomplete` CLI state; machine-safe output; changed selected skill changes release identity.
  - Dependencies: no live service; do not conflate with OTel export, streaming or provider profile change.
  - Acceptance: deterministic fake-chain/validator/function-model and CLI fixtures. Parent must run them.

- **Phase 2 — Complete evaluability and establish honest cohorts (medium; P0/P1).**
  - Components: Reviewer manifest/evaluator/cases; grouped development/holdout manifests; mode/provenance schema; completion and p95 reporting; native trajectory/span adapter only if local tracing is approved.
  - Deliverables: every role appears in `make eval`; no out-of-scope policy pass; separate scripted/live-model-fixture/live-workspace/e2e reports; dataset admission schema.
  - Dependencies: Phase 0 accounting; approved trace-retention decision for span evaluators; no live baseline threshold until a held-out cohort is frozen.
  - Acceptance: scripted results are labeled plumbing only. Provider and Docker baselines remain pending parent/operator scheduling.

- **Phase 3 — Native durable operational correctness (medium/large, isolated; P0/P1).**
  - Components: explicit Temporal architecture decision; startup durable-agent registration or formal spec amendment; retry ledger; heartbeat/cancellation; shared artifact resolver; release-derived Worker Versioning; replay fixture gate; fleet-capacity declaration.
  - Deliverables: per-model/tool activity parity if native route selected, terminal cancellation receipt, artifact portability, pinned routing proof and no blind re-execution after uncertainty.
  - Dependencies: Phase 1 release identity; Temporal test server; non-production Temporal deployment for final routing/cancellation/cross-worker qualification.
  - Acceptance: first test-server deterministic model/tool evidence, then replay, then controlled non-production evidence. No production claim or speed claim follows automatically.

- **Phase 4 — Existing Docker evidence hardening and live baselines (medium/large).**
  - Components: source snapshot/re-hash, image lock/admission, command receipts, cleanup/reaper, stream-loss typed outcome, disposable real-workspace cohorts, small external corpus admission samples.
  - Deliverables: evidence-complete Docker rows and three-repeat paired live baseline receipts per admitted case/language.
  - Dependencies: Phase 2 mode/gate fixes, operator provider credentials/process, selected images/matrix rows.
  - Acceptance: predeclared thresholds are confirmed against untouched held-out live results with coverage and uncertainty, without tuning on that cohort. The current audit supplies none.

- **Phase 5 — OpenShell Docker-driver qualification, then optional kind (large, deferred).**
  - Components: explicit version tuple/policy lock, thin backend adapter, driver-specific qualification suite, no-fallback selection, row-by-row parity comparison.
  - Deliverables: policy allow/deny evidence, typed stream/uncertain outcomes, deletion waits and matching Corsair receipts.
  - Dependencies: `SPEC-0082` e2e/baseline gates plus Phase 4 evidence; kind adds a separate CNI/kernel/driver decision.
  - Acceptance: only after per-row canary/replay/probe/e2e parity. Delete Docker mechanics only when equivalent evidence exists.

## 8. Delivered patch, experiments and remaining work

This audit was carried through a bounded implementation on `audit/develop-quality-20261014`, based on the target `develop` revision. No changes were merged to `develop` or `main` and no production service or runtime was deployed. The code uses the existing argparse/native Pydantic Evals/recorder interfaces and a direct **Rich 15.0.0** pin; no additional CLI framework, trace parser, provider protocol, scheduler or skill loader was introduced.

### Fixed in the patch

- **Evaluation scope:** a live-only or wrong-set policy returns `not_applicable` before thresholds. Frozen policy files and promotion behavior are unchanged.
- **Operational coverage:** new attempt rows distinguish task and evaluator failures. Summaries expose attempted/completed coverage and evaluator failures by language/kind, without converting conditional semantic quality into an end-to-end score. Historical unattributed failures keep completion unknown. Optional completion/evaluator hard gates can now be evaluated; they are not enabled automatically.
- **CLI:** stage start/terminal events, one native indeterminate Rich spinner on interactive terminals, scrolling stderr logs, `NO_COLOR`, deterministic non-TTY output, recorded per-agent token/request/tool/retry/latency aggregates and clean versioned JSON output. Missing/malformed root records return exit 2; incomplete records do not imply active work. Per-tool timing and live token deltas remain follow-ons, not fabricated from aggregate counters.
- **Direct lifecycle:** cancellation records the last observed stage and stop time, retains null finish time and no verdict. JSON cancellation emits one object with `verdict: null`, unknown aggregate totals, and exit 130. A client interruption does not claim a remote command/workflow terminated or cleanup succeeded.
- **Developer golden path:** `make test-config` works; the five canonical skills use current v2 paths and one architecture authority. Codex symlinks are preserved. The living development guide now uses real Make flags and verified dynamic v2 scorer discovery. Structural guards do not certify actual Claude/Codex compliance.

### Observed validation

The original locked Python 3.12 baseline passed **1,484 tests with 50 skips**. Initial focused patch checks passed **167 tests**. The first full patch run exposed an existing test that demanded a live-only policy pass on scripted data; that assertion was corrected to require `not_applicable`, with a separately scoped unit policy retaining threshold checks. That post-correction suite passed **1,510 tests with 50 skips**, both with four workers and serially.

Independent review then reproduced an empty JSON stdout stream on direct cancellation and two inaccurate skill instructions. The cancellation envelope and instructions were corrected and an actual all-local SIGINT probe confirmed **one cancellation JSON value and exit 130**, without any model/provider, Docker or Temporal dependency. Final reconciled focused checks passed **152 tests**; the integrated source passed **1,649 tests with 113 skips**, both four-worker (54.90s) and serial (131.46s). Native Temporal test-server fixtures ran; Docker/kind/gateway/platform skips remain unqualified. Independent per-PR counts are separately recorded after the requested split. PLAN-0101/HANDOFF-0137 and the audit bundle retain these actual runs, not only the earlier intermediate results.

Existing Temporal test-server workflow tests ran successfully with deterministic stage/model fixtures; they are not production routing, per-model/tool native durability, cross-worker storage, crash recovery or cancellation/cleanup qualification. Docker is unavailable here: a targeted qualification subset had **27 passed and 45 Docker/image-related skips**. The broader suite's 50 skips remain explicitly excluded from qualified behavior.

The six available scripted evaluation commands were re-run without provider configuration: Grounding **85/85**, Investigator **91/91**, Builder **57/57**, Control Prober **65/65**, Exploit Prober **70/70**, and chain **100/100** clean attempts. These test plumbing/oracle replay, not model accuracy or native vulnerability dispositions. All live-only policies correctly reported `not_applicable`; no baseline was promoted. That statement describes the starting snapshot: upstream subsequently added the Reviewer set, and its reconciled scripted result is recorded with the final evidence.

### Observed scripted breadth by language

Final reconciled commands cover all seven roles below. These are completed oracle-replay attempts, not inference accuracy or qualified native vulnerable/fixed issue pairs.

| Role | Python | Java | JavaScript | Ruby | Perl | Common |
| --- | --- | --- | --- | --- | --- | --- |
| grounding | 15 | 15 | 15 | 15 | 15 | 10 |
| investigator | 17 | 18 | 17 | 19 | 19 | 1 |
| builder | 10 | 13 | 12 | 11 | 11 | — |
| control_prober | 13 | 13 | 13 | 13 | 13 | — |
| exploit_prober | 14 | 14 | 14 | 14 | 14 | — |
| reviewer | 26 | 33 | 33 | 33 | 32 | — |
| chain | 37 | 11 | 18 | 15 | 15 | 4 |

All seven commands were clean; live-only policies returned `not_applicable` and no baseline was promoted. Reviewer 157/157 is newly provided upstream, not an audit-created corpus. Per-language completion and dimension counts are retained in the evidence JSON.

### Local Qwen result: no basis for prompt promotion

A separate explicitly requested CPU-only experiment used the official pinned **Qwen3-1.7B Q8_0 GGUF** and **llama.cpp b11612** on loopback. Normal Corsair provider policy/configuration and agent prompts were unchanged. Its harmless native tool/typed-output preflight passed: **2 model requests, 1 tool call, 494 input and 25 output tokens**.

The actual Investigator was then tried on two frozen Python development cases with current and compact instructions, eight-request/six-tool caps and a 180-second deadline. **All four episodes timed out without a final plan.** Conditional accuracy and full episode token cost therefore remain unknown, not zero. Captured response prefixes showed lower input tokens for the compact instructions but different trajectories; that does not establish a complete-run efficiency win. No production prompt changed. The detailed experiment note and reproducible scripts/identities are in the audit bundle; model binaries/weights are excluded, and the temporary server is no longer serving.

### Next bounded changes

1. Preserve the upstream D3 re-check loop and strengthen Reviewer negative citation/feedback bounds plus exploit counterfactual validation.
2. Build on the new upstream Reviewer evaluator: document p95/sample/paired-statistics semantics, complete mode/provenance separation and independently admitted grouped holdouts. Thresholds must be predeclared from development/validation data and confirmed on holdout without retuning.
3. Resolve native Temporal per-operation durability versus formal stage-level design, then use native retry/heartbeat/versioning/replay controls with shared artifact resolution.
4. Add source/image admission, redacted command receipts, cleanup confirmation and stream-uncertainty tests on the current Docker backend. Qualify representative real-workspace issue pairs and collect per-language token/latency/accuracy trade-offs.
5. Follow the latest explicit gate decisions to qualify the implemented OpenShell 0.1.3 adapter and policy tuple; do not create a competing backend. Keep Docker until equivalent row-by-row evidence exists.

## 9. Current OpenShell adapter: reuse is largely correct; tighten its evidence and authority

A bounded review of the official pinned **0.1.3 wheel** and immutable `06d4cbe` source confirms the implemented port already uses native lifecycle/exec, explicit backend selection, digest-mapped images, policy application/readback and fresh replayed probe environments. There is **no native policy-management or file-transfer API at this pin** to remove the current CLI/tar seams. Replacing them with assumed 0.1.4 APIs would be an upgrade, not simplification. Keep the thin required glue and fix the following controls before claiming parity/live qualification.

| Priority | Current finding | Bounded next change and source |
| --- | --- | --- |
| P1 | Builder `destroy()` confirmation is awaited then discarded. | Carry confirmed/false cleanup into the run record/`cleanup_unconfirmed` and reaper ownership. [Builder seam](https://github.com/X-McKay/corsair/blob/06d4cbe21b891051811f80559a478881c061ee86/src/corsair/v2/chain.py#L198-L217); native removal confirmation is in `workspace/openshell.py:642-671,924-926`. |
| P1 | Missing local generation records allow adoption/removal of a same-name, Corsair-labelled sandbox. Name/label ownership is not immutable identity. | Bind native `SandboxRef.id` into durable workspace references/registry and require its match on every get/delete, including record-absent paths. Add negative tests that prove no policy application/adoption/deletion on missing or changed generation. [Ownership/adoption](https://github.com/X-McKay/corsair/blob/06d4cbe21b891051811f80559a478881c061ee86/src/corsair/v2/workspace/openshell.py#L353-L366), `:642-671,801-829`; this uses the existing 0.1.3 id, not a new SDK. |
| P1 | Effective-policy validation permits broadened filesystem shapes and unrequested non-empty `process` authority. | Qualify and lock filesystem roots/flags plus an explicit safe process policy or exact live-qualified gateway default; reject simultaneous broadening of both documents and injected process grants. [Policy verifier](https://github.com/X-McKay/corsair/blob/06d4cbe21b891051811f80559a478881c061ee86/src/corsair/v2/workspace/openshell.py#L139-L186), `:249-254`. Do not infer gateway defaults before the exec-user/readback gate. |
| P2 | Source bytes are copied before an immutable intake-hash check; OpenShell detects changed bytes only at later environment open. | Rehash/snapshot immediately before copy/cache population and test mutation-before-replay on both backends. `build.py:68-114`; `workspace/openshell.py:697-726`. |
| P2 | Native chunk/exit observations do not produce the required durable Corsair command receipts. | Keep a small redacted, append-only domain receipt for argv, name/id, policy/image/source digest, timing and completed/timed-out/uncertain delivery. The 0.1.3 exec API has no durable request-id/outcome facility to replace it. `workspace/openshell.py:733-772`; SPEC-0082 `commands.jsonl`. |

These are source-confirmed opportunities, **not changes silently folded into the CLI PR**. Native gateway enforcement, Landlock/workdir, command user, stdin/exit-124 behavior, CLI JSON/image fields, TLS/binary policy, resource shape and backend verdict parity remain unrun here. Follow SPEC-0083's latest coordinator/gate decisions. The detailed late-delta review is retained in the evidence bundle.

## 10. Independent review units

At the user's request, the delivered code is separated into three independently base-aligned draft PRs: **evaluation accounting/policy scope**, **CLI presentation/JSON/direct lifecycle**, and **shared developer skills/golden-path checks**. A fourth **documentation-only audit/benchmark-roadmap PR** carries the source report and central handoff. Each code PR has its own plan/current-work entry and standalone focused, serial/four-worker, cleanup and post-cleanup validation. None requires cherry-picking another code PR to test. The combined reviewed source is also packaged, clearly separate from the individual PRs and from private raw experiment evidence.

No native Temporal migration, new OpenShell backend, production prompt, public benchmark accuracy, or release-baseline promotion is presented as implemented. Those proposals require the explicit design/evidence steps above rather than large speculative changes in an unrelated PR.

## Remaining qualification limits

- The research findings refer to read-only workstream inspection of the base revision. The separate bounded patch and CPU-only local inference experiment are reported in the delivery section. No production provider, Docker/kind/OpenShell workload, production credential, OTel collector, or external benchmark execution was performed.
- Exact pinned PydanticAI/Harness wheel source was inspected in the Pydantic workstream for selected API claims; many linked vendor documents are current docs-head and are cited as capability context, not proof that an unexecuted integration works at the pin.
- Deterministic local reproductions establish the direct cancellation and nonexistent-run comparison seams; they do not qualify Temporal cancellation, worker crash/acknowledgement loss, Docker stream failure root cause, cross-host artifacts, worker version routing, capacity, endpoint compatibility, model quality, latency or cost.
- Existing scripted evaluation fixtures establish contract/oracle/replay wiring and leakage checks, not inference accuracy, native workspace behavior or benchmark generalization. Representative live disposition accuracy and full-run token/latency trade-offs remain unknown; the limited local experiment cannot establish them.
- OpenShell v1 evidence is historical and excludes v2 PydanticAI/Temporal/adapters/interruption/recovery qualification. Its platform logs remain supplemental, not Corsair verdict evidence.

## References

1. [PydanticAI Agent Specs documentation](https://ai.pydantic.dev/agent-spec/)
2. [PydanticAI Harness Skills documentation](https://ai.pydantic.dev/harness/skills/)
3. [PydanticAI retry and usage-limit documentation](https://ai.pydantic.dev/retries/)
4. [PydanticAI Workspace backend documentation](https://pydantic.dev/docs/ai/core-concepts/workspace/)
5. [PydanticAI compatible OpenAI APIs and model profiles](https://pydantic.dev/docs/ai/models/compatible-apis/)
6. [PydanticAI Harness Tool Output Limits](https://pydantic.dev/docs/ai/harness/tool-output-limits/)
7. [PydanticAI durable execution with Temporal](https://pydantic.dev/docs/ai/capabilities/durable_execution/temporal/)
8. [Temporal Python workflow cancellation](https://docs.temporal.io/develop/python/workflows/cancellation)
9. [Temporal Python activity timeouts and heartbeats](https://docs.temporal.io/develop/python/activities/timeouts)
10. [Temporal External Storage](https://docs.temporal.io/external-storage)
11. [Temporal Worker Versioning](https://docs.temporal.io/production-deployment/worker-deployments/worker-versioning)
12. [Temporal Python error handling and idempotency](https://docs.temporal.io/develop/python/best-practices/error-handling)
13. [Temporal Python Worker configuration](https://docs.temporal.io/develop/python/workers/run-worker-process)
14. [NVIDIA OpenShell overview](https://docs.nvidia.com/openshell/about/overview)
15. [NVIDIA OpenShell architecture](https://docs.nvidia.com/openshell/about/architecture)
16. [NVIDIA OpenShell sandbox logging](https://docs.nvidia.com/openshell/observability/logging)
17. [NVIDIA OpenShell support matrix](https://docs.nvidia.com/openshell/about/support-matrix)
18. [NVIDIA OpenShell network rules](https://docs.nvidia.com/openshell/how-it-works/policies/network-rules)
19. [NVIDIA OpenShell API errors and deletion outcomes](https://docs.nvidia.com/openshell/sdk/api-errors)
20. [Pydantic Evals core concepts](https://pydantic.dev/docs/ai/evals/getting-started/core-concepts/)
21. [Pydantic Evals agentic evaluators](https://pydantic.dev/docs/ai/evals/evaluators/agentic/)
22. [Pydantic Evals span-based evaluators](https://pydantic.dev/docs/ai/evals/evaluators/span-based/)
23. [Vul4J primary repository](https://github.com/tuhh-softsec/vul4j)
24. [NIST Juliet Java 1.3](https://samate.nist.gov/SARD/test-suites/111)
25. [OWASP Benchmark project](https://owasp.org/www-project-benchmark/)
26. [OpenSSF CVE Benchmark primary repository](https://github.com/ossf-cve-benchmark/ossf-cve-benchmark)
27. [CVEfixes Dataset Zenodo v1.0.8 immutable version record](https://zenodo.org/records/13118970)
28. [PrimeVul primary repository](https://github.com/DLVulDet/PrimeVul)
29. [Big-Vul / MSR-20 primary repository](https://github.com/ZeoVan/MSR_20_Code_vulnerability_CSV_Dataset)
30. [DiverseVul primary repository](https://github.com/wagner-group/diversevul)
31. [PydanticAI prompt caching documentation](https://ai.pydantic.dev/capabilities/caching/)
32. [PydanticAI Instrumentation capability](https://pydantic.dev/docs/ai/capabilities/instrumentation/)
33. [OpenTelemetry Python manual instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/)
34. [Rich Console API](https://rich.readthedocs.io/en/latest/console.html)
35. [Rich Progress Display](https://rich.readthedocs.io/en/latest/progress.html)
36. [Claude Code Skills documentation](https://code.claude.com/docs/en/skills)
37. [OpenAI Codex Build skills](https://developers.openai.com/codex/skills/)
38. [Ruff documentation](https://docs.astral.sh/ruff/)
39. [ty documentation](https://docs.astral.sh/ty/)
40. [llama.cpp HTTP server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)

[1]: https://ai.pydantic.dev/agent-spec/ "PydanticAI Agent Specs documentation"

[2]: https://ai.pydantic.dev/harness/skills/ "PydanticAI Harness Skills documentation"

[3]: https://ai.pydantic.dev/retries/ "PydanticAI retry and usage-limit documentation"

[4]: https://pydantic.dev/docs/ai/core-concepts/workspace/ "PydanticAI Workspace backend documentation"

[5]: https://pydantic.dev/docs/ai/models/compatible-apis/ "PydanticAI compatible OpenAI APIs and model profiles"

[6]: https://pydantic.dev/docs/ai/harness/tool-output-limits/ "PydanticAI Harness Tool Output Limits"

[7]: https://pydantic.dev/docs/ai/capabilities/durable_execution/temporal/ "PydanticAI durable execution with Temporal"

[8]: https://docs.temporal.io/develop/python/workflows/cancellation "Temporal Python workflow cancellation"

[9]: https://docs.temporal.io/develop/python/activities/timeouts "Temporal Python activity timeouts and heartbeats"

[10]: https://docs.temporal.io/external-storage "Temporal External Storage"

[11]: https://docs.temporal.io/production-deployment/worker-deployments/worker-versioning "Temporal Worker Versioning"

[12]: https://docs.temporal.io/develop/python/best-practices/error-handling "Temporal Python error handling and idempotency"

[13]: https://docs.temporal.io/develop/python/workers/run-worker-process "Temporal Python Worker configuration"

[14]: https://docs.nvidia.com/openshell/about/overview "NVIDIA OpenShell overview"

[15]: https://docs.nvidia.com/openshell/about/architecture "NVIDIA OpenShell architecture"

[16]: https://docs.nvidia.com/openshell/observability/logging "NVIDIA OpenShell sandbox logging"

[17]: https://docs.nvidia.com/openshell/about/support-matrix "NVIDIA OpenShell support matrix"

[18]: https://docs.nvidia.com/openshell/how-it-works/policies/network-rules "NVIDIA OpenShell network rules"

[19]: https://docs.nvidia.com/openshell/sdk/api-errors "NVIDIA OpenShell API errors and deletion outcomes"

[20]: https://pydantic.dev/docs/ai/evals/getting-started/core-concepts/ "Pydantic Evals core concepts"

[21]: https://pydantic.dev/docs/ai/evals/evaluators/agentic/ "Pydantic Evals agentic evaluators"

[22]: https://pydantic.dev/docs/ai/evals/evaluators/span-based/ "Pydantic Evals span-based evaluators"

[23]: https://github.com/tuhh-softsec/vul4j "Vul4J primary repository"

[24]: https://samate.nist.gov/SARD/test-suites/111 "NIST Juliet Java 1.3"

[25]: https://owasp.org/www-project-benchmark/ "OWASP Benchmark project"

[26]: https://github.com/ossf-cve-benchmark/ossf-cve-benchmark "OpenSSF CVE Benchmark primary repository"

[27]: https://zenodo.org/records/13118970 "CVEfixes Dataset Zenodo v1.0.8 immutable version record"

[28]: https://github.com/DLVulDet/PrimeVul "PrimeVul primary repository"

[29]: https://github.com/ZeoVan/MSR_20_Code_vulnerability_CSV_Dataset "Big-Vul / MSR-20 primary repository"

[30]: https://github.com/wagner-group/diversevul "DiverseVul primary repository"

[31]: https://ai.pydantic.dev/capabilities/caching/ "PydanticAI prompt caching documentation"

[32]: https://pydantic.dev/docs/ai/capabilities/instrumentation/ "PydanticAI Instrumentation capability"

[33]: https://opentelemetry.io/docs/languages/python/instrumentation/ "OpenTelemetry Python manual instrumentation"

[34]: https://rich.readthedocs.io/en/latest/console.html "Rich Console API"

[35]: https://rich.readthedocs.io/en/latest/progress.html "Rich Progress Display"

[36]: https://code.claude.com/docs/en/skills "Claude Code Skills documentation"

[37]: https://developers.openai.com/codex/skills/ "OpenAI Codex Build skills"

[38]: https://docs.astral.sh/ruff/ "Ruff documentation"

[39]: https://docs.astral.sh/ty/ "ty documentation"

[40]: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md "llama.cpp HTTP server README"
