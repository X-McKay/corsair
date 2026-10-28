# Recipe free investigation design

Status: scope expanded by the user on 2026-10-27. The user explicitly authorized replacing recipes throughout investigations and allowing agents to author test code and commands executed only inside the configured sandbox. This supersedes PLAN-0130's recipe-bound handoff. The concrete execution and outcome design below was approved by the user’s “Please continue” on 2026-10-27; implementation is tracked in [PLAN-0133](PLAN-0133-recipe-free-implementation.md).

## Intent

An operator supplies an issue and source, rather than a predefined language/property recipe. Intake identifies requirements and selects an available image. A producer constructs a bounded test plan; trusted execution records what actually ran; an independent outcome-blind auditor reviews the plan's semantic relationship to the issue. Temporal owns rounds and durability, and ADK owns model episodes.

The removal is architectural, not a rename of Recipe to Plan. No fixed disclosure callable, payload slot, expected control, allowed-exception list or language-specific recipe union is required by a new investigation.

## Execution contract

Add canonical SDK-free models under `contracts/execution.py`:

- `ExecutionRequest`: version, case ID, normalized issue, source, selected available image identity, optional fixed source, budget and intake provenance. A direct request is revalidated against trusted source and image admission, not trusted because it contains an image ID.
- `TestFile`: normalized relative path and bounded UTF-8 code. Files are materialized only beneath the container's writable work directory, never on the host as executable tests and never over the read-only admitted source.
- `Command`: an explicit argv list, relative work directory and bounded timeout. No host shell interpolation. An agent can explicitly choose an in-container shell command; that shell has only the configured container permissions.
- `TestPlan`: hypothesis, revision/parent revision, test files, ordered commands, source locations and categorical expected command outcomes. This is proposed executable material, never an observation or a security verdict.
- `CommandReceipt`: actual argv identity, container identity, start/completion state, native exit status, bounded stdout/stderr artifact references and truncation flags.
- `ProcessObservation`: source, image and plan digests, actual command receipts, cleanup status, operation/artifact identities and explicit operational failures.
- `ExecutionResult`: version 3 report with execution outcome, independent semantic audit, immutable evidence references, scoped limitations and usage. Command outcome and security assessment are separate fields.

Initial ceilings: 16 files, 32 KiB per file, 128 KiB total code; 8 commands, 64 argv elements per command, 32 KiB combined argv; each command bounded by the remaining request/probe deadline. Existing root model/tool/round/time ceilings remain authoritative. No model-supplied environment variables, mounts, container security settings, credentials or registry addresses are execution capabilities.

## Available image capabilities

Intake v2 and execution admission contain no recipe field or investigation-binding requirement. Available-image inventory entries describe reviewed language, execution mode and tooling capabilities. Requirements are matched against that inventory and operator policy. Images cannot grant network or privileged permissions through metadata.

Recommendations and execution must use currently available, operator-permitted images; no model-driven pulls, builds or registry discovery. Resolve and recheck immutable image identity before executing. The existing Python/Node/Java images can supply their installed tools without selecting their historical disclosure drivers. Additional locally available images require explicit operator configuration and reviewed metadata; presence alone does not establish suitability or qualification.

`in_scope_supported` is intake compatibility with the configured environment. It does not authorize a command, establish a vulnerability or prove that a generated test will succeed. Source/image changes require new admission and configuration identity.

## Agent execution

The current producer role gains a native factory for `TestPlan` decisions with read-only source tools. It can inspect the source and construct tests in any language supported by the selected environment. Packaged instructions are loaded from the installed package; no runtime skill runs scripts or provisions an environment.

Mandatory bounded source context is read inside the inspection sandbox and clearly recorded as trusted preload. Model-requested source calls are accounted separately. A model may not cite an unread path as inspected source. Tool and output budgets include the preload cost; truncation remains explicit.

The auditor receives issue, source context and the complete proposed plan, never observations or evaluator labels. It can veto a plan that does not exercise the reported mechanism, overwrites/copies and changes the target, asserts an unrelated property, accesses private evidence directly or lacks necessary context. Acceptance does not grant permissions or certify execution.

There is no custom agent loop. A finite Temporal round runs producer, auditor and execution activities. An operational failure or rejected plan stays explicit. Mechanical command-exit/error feedback may inform a later producer revision, bounded by the same root budget; it carries no exploitability label.

## Trusted generic sandbox execution

Implement a concrete generic Docker executor alongside the inspection adapter. It overrides image entrypoints with a fixed reviewed idle command for the supported Linux tool images and executes the model's argv only through the Docker SDK inside that container.

- `/source` is the immutable admitted source mount, read-only.
- `/work` and `/tmp` are bounded writable container work areas. Test files enter through trusted safe archive construction, not host execution.
- Network remains disabled; no Docker socket, host credentials or model-selected mounts. Drop capabilities, use non-root UID, read-only image filesystem and CPU/PID/memory/time limits.
- Observer/controller code stays outside agent control. Actual Docker exec exit status and stdout/stderr are recorded by trusted host code.
- Container ownership, cleanup and uncertain-operation refusal remain bound to immutable container ID. Cancellation waits for setup reconciliation and cleanup. No exactly-once or full host-loss continuation claim.
- Model-authored JUnit/coverage/JSON files are untrusted artifacts. They cannot be accepted as trusted native security observations merely because they resemble an old driver report.

A command can fail because of missing packages or unsupported tooling; the executor records that failure. It never installs target dependencies on the host, opens network implicitly, changes provider or selects another image to hide the failure.

## Outcome semantics requiring review

Trusted code can establish that a particular plan ran against a particular admitted environment, returned particular process outputs and exit statuses, and was cleaned up. It cannot establish that arbitrary model-authored assertions are correct merely because the process exited zero.

Proposed initial behavior:

- Report `SUCCEEDED`, `FAILED`, `ERROR` or `INCOMPLETE` for actual command execution.
- Record accepted/rejected/insufficient semantic audit separately.
- A successful, accepted generated reproduction is conditional evidence for review; it does not automatically inherit the old disclosure recipe's `DEMONSTRATED` or finite-protocol `NOT_DEMONSTRATED` meaning.
- Keep a security assessment unresolved until independently admissible observations establish the claimed property. Failed reproduction never grants clearance.

This preserves useful agent-authored reproduction artifacts while avoiding a false claim that a generated test is its own independent security oracle. Adding generic trusted property observations is a separate bounded capability, not a hidden recipe requirement for intake or command execution.

## Migration

New CLI/API investigations use the recipe-free versioned contract and generic executor. New agent packets, source preparation, image selection, manifests, active workflow, audit and evidence recording do not require a recipe.

Historical compatibility covers decoding results, replaying recorded histories and frozen evaluations, not resumption of old in-flight investigations. New execution workflows use a separate versioned identity; historical workflow/activity names and payload shapes stay stable.

For optional fixed source, reuse the exact accepted plan against a separately admitted fixed snapshot in a fresh container. Report a process comparison, with security and patch effectiveness unresolved. A revised plan is a separate experiment with its own identity.

Unchanged copies of source into `/work` may be needed for compilation. Record their admitted origin; generated code, reports, exit conventions and stdout remain untrusted content. Trusted process receipts stay outside the container. The read-only mount does not prove arbitrary tests exercised the source.

Existing immutable result/1 and result/2 artifacts, frozen fixtures and recorded Temporal histories retain their exact interpretation. Retain the minimal historical schema/observer/workflow code needed to decode, replay and evaluate them, clearly marked as legacy. Keep that path out of new investigation admission; do not silently translate old receipts into version 3 claims or rewrite old cohort labels.

The original intake recipe-bound cohort remains a historical diagnostic. `evals/datasets/intake-capabilities.json` is a new cohort for recipe-free classification; old inputs/oracles and failed live results remain preserved. No baseline denominator or oracle is changed to turn an earlier failure into a pass.

## Implementation and verification

1. Complete recipe-free intake v2 contracts, policy and candidate scoring; verify available-image selection and denied-permission behavior.
2. Define execution contracts and unit tests for path/argv/code/deadline bounds and request/image/source identity.
3. Implement generic Docker execution and actual native tests for stdout/stderr/exit capture, read-only source, no host execution, limits, cancellation, cleanup and uncertain operations.
4. Add native producer/auditor factories and frozen independent role cohorts. Preserve historical factories/resources only where historical decoding/evaluation needs them.
5. Wire the versioned Temporal workflow, explicit worker composition and CLI/API; exercise actual ADK/Docker/Temporal composition and replay independently from live-model quality.
6. Update current documentation, review boundaries, remove owned dead code, rerun affected consumers and frozen diagnostics, run `just check`, build and inspect the wheel, and verify installed resources outside the checkout.

The live model selected by the user is Qwen3.6-35B-A3B-NVFP4 at `https://llm.almckay.io/v1`. Native OpenAI-compatible schema output and the hosted-vLLM tool-completion route have different observed conformance. All failed diagnostics and route/configuration identities remain distinct; no string-to-object repair is added.
