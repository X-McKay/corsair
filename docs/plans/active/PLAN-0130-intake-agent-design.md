# Intake agent implementation design

Status: original intake design approved for implementation on 2026-10-27. Its recipe bindings and unchanged-investigation scope were subsequently superseded by the user’s recipe-removal instruction and [PLAN-0132](PLAN-0132-recipe-free-investigations.md). Current intake v2 behavior is documented in [the intake guide](../../agents/intake.md); this record retains the earlier design context.

## Intent and agreed direction

Accept an issue reference or varied issue JSON, inspect an admitted repository in a fixed inspection sandbox, and produce a structured assessment with an image recommendation. Use categories rather than prose rationale so primary metrics over frozen human-reviewed cases can be scored deterministically. Full arbitrary-text normalization fidelity still requires human review.

Intake identifies what an issue requires independently of current execution support. An absent recipe must not prevent useful analysis. Image recommendations are restricted to the currently available, operator-permitted local images supplied by trusted code; absence of a suitable image produces a null recommendation. Trusted code compares the proposed requirements with concrete implemented execution capabilities. Intake does not investigate exploitability or create evidence.

Keep one ADK role and one ordinary bounded episode per request. The episode normalizes the issue and analyzes the repository together. Already canonical issue input can bypass model normalization, but still receives analysis. Separate evaluation inputs allow normalization and analysis quality to be measured independently.

## Approaches considered

1. Recipe-first intake: select an existing recipe and its image. Simple to admit, but conflates understanding an issue with today's narrow coverage. Rejected in discussion.
2. Multiple normalization, analysis, and admission agents with detailed prose/provenance records. Flexible, but exceeds the requested simplicity and complicates scoring. Rejected in discussion.
3. One structured intake role, image recommendation, and trusted admission checks. This is the direction accepted in discussion; the concrete defaults below remain proposals for review.

## Initial boundary and proposed defaults

- Exactly one issue per request. Multiple apparent findings produce `MULTIPLE_ISSUES`; do not silently merge or select one.
- Local repository source is required and admitted independently of issue content. An issue URL cannot select a host path or authorize remote checkout.
- Implement one real provider: GitHub issue lookup using an explicit owner, repository, and positive issue number. A number alone requires configured repository context. Other providers are future concrete extensions, not placeholder adapters.
- Retrieve only the issue title and body plus identity metadata initially. Comments, attachments, redirects to arbitrary hosts, and linked pages are not fetched. GitHub credentials remain in the worker environment.
- Scope defaults to authorized repository security issues, across languages and affected surfaces. Feature requests and non-security maintenance are out of scope. Authorization and repository boundaries are operator-owned, not inferred from issue text. This scope policy needs approval with the design.
- No target execution, package installation, repository Dockerfile build, image pull, or automatic investigation start. Image recommendation is useful even when execution is unsupported.
- Recommend only from a trusted snapshot of currently available local images. Do not invent image references, suggest registry alternatives, or assume that an absent configured image is available.
- Existing producer, auditor, investigation requests, and workflow history behavior remain unchanged.

## Canonical contracts

Define the new models once in `contracts/intake.py`, inheriting the existing frozen, extra-forbidden `Contract`. Public exports and role-local identity re-exports follow current conventions. Enum strings below are proposed wire values; changing a taxonomy changes schema/configuration identity.

### Input

`IntakeRequest` contains a version, a discriminated `input`, a `Source`, an intake budget, and optional operator-authored investigation bindings for execution compatibility checking. Bindings contain an existing `InvestigationRequest` and an explicit operator attestation tying its digest to this issue input digest. Its source must bind to the same snapshot and its finding/recipe file must appear among grounded locations. Operator attestation supplies the authority that the recipe addresses this issue; same-snapshot coincidence alone is insufficient. Intake may flag a conflicting binding as `REQUIRED_INPUT_MISSING`; it cannot manufacture attestation or grant extra access. Semantic binding quality remains part of human review and false-supported evaluation.

The two input variants are:

- `issue_reference`: explicit GitHub owner/repository/number, or number with operator repository context resolved before scheduling.
- `json`: a bounded JSON value, not an executable command or a filesystem pointer supplied by the issue.

Parse JSON syntax before model invocation. Accept valid JSON shapes but return `INSUFFICIENT_ISSUE_INFORMATION` for unrelated or insufficient content. Do not attempt string repair. Reject oversized/deep input before provider/network/model work: initial limits are 64 KiB UTF-8 JSON, nesting depth 16, and 256 object/list entries per container. Reject duplicate JSON object keys rather than silently losing conflicting values.

`Issue` has only `title: str | None`, `description: str | None`, and `locations: list[Location]`. A location has a normalized relative `path` and optional `symbol`. Title and description are the report, not verified repository facts. Missing fields remain null/empty; never default to a fabricated title or description. An already canonical issue is deterministically validated and copied unchanged.

Proposed bounds: title 500 characters, description 12,000 characters, 16 locations, path 240 characters, symbol 240 characters. Do not silently truncate an over-limit report into an apparently complete one. Preserve an attributable input-limit failure.

The raw input and fetched response are private immutable artifacts after admission. They are not unrestricted model context: existing source restrictions, secret handling, and oracle separation apply. Evaluation oracles are always separate artifacts, never JSON input fields. Unknown fields need not be copied into normalized output; preserve the original reference for review.

### Agent output

`IntakeProposal` is the native `LlmAgent.output_schema`. It contains:

| Field | Type and meaning |
| --- | --- |
| `issue` | Canonical normalized `Issue`. |
| `scope` | `in_scope`, `out_of_scope`, `unknown`; semantic recommendation under the supplied policy. |
| `surface` | `function`, `component`, `configuration`, `dependency`, `application`, `unknown`. |
| `language` | `python`, `javascript`, `typescript`, `java`, `go`, `rust`, `c`, `cpp`, `shell`, `other`, `multiple`, `unknown`. |
| `execution_mode` | `callable`, `command`, `http_service`, `application`, `static_configuration`, `unknown`. |
| `requirements` | Unique enum list defined below. Empty means none identified, never proof none exist. |
| `suggested_image` | One exact canonical image reference from the supplied available-image inventory, or null. A recommendation, not execution permission. |
| `reason_codes` | Unique semantic/input reason codes; no prose rationale. |
| `locations` | Up to 16 repository-grounded locations supporting the assessment. |

Initial requirement enum: `dependency_install`, `build`, `service_start`, `http_client`, `external_service`, `network_access`, `native_toolchain`, `browser`, `privileged_execution`, `other`, `unknown`.

Initial agent reason enum: `OUTSIDE_SCOPE_POLICY`, `INSUFFICIENT_ISSUE_INFORMATION`, `MULTIPLE_ISSUES`, `SOURCE_LOCATION_UNRESOLVED`, `REQUIREMENTS_UNRESOLVED`, `IMAGE_UNDETERMINED`, `NO_COMPATIBLE_IMAGE`.

Use null plus `NO_COMPATIBLE_IMAGE` when requirements are understood but no supplied image fits; use `IMAGE_UNDETERMINED` when information is insufficient to select an image. A reference outside the supplied inventory is invalid output, not an alternative recommendation.

Use `unknown`/`other` explicitly when a taxonomy cannot express a case. These values cannot satisfy admission. Repository references must exist in the snapshot; symbol correctness is scored separately and is not established by path validation. Reported issue locations and grounded analysis locations remain distinct.

### Recorded result

`IntakeResult` adds trusted fields to the validated proposal:

- `schema_version: corsair.intake-result/1` and `run_id`.
- `status: completed | needs_input | error`.
- `classification: in_scope_supported | in_scope_not_supported | out_of_scope | null`.
- A proposal, or null if no valid model output exists.
- Combined sorted reason codes, including trusted blockers.
- `image_check: not_checked | accepted | blocked | unavailable` and nullable resolved immutable image identity.
- Input/source/image-inventory/configuration/policy/capability/model/resource identities, existing `Usage`, and result artifact reference.

Use one bounded operational error enum alongside status: `INPUT_INVALID`, `INPUT_LIMIT_EXCEEDED`, `ISSUE_FETCH_FAILED`, `SOURCE_DENIED`, `INSPECTION_FAILED`, `MODEL_FAILED`, `OUTPUT_INVALID`, `IMAGE_CHECK_FAILED`. Do not put provider error text or model reasoning into the classification fields. Sanitized diagnostics follow the existing operational boundary.

The CLI emits this record as JSON. The assessment fields are compact; the embedded normalized issue can contain the full bounded description. Human display can explain enum values without adding generated rationale to the canonical output.

## Classification and image admission

The agent recommends scope and requirements. Pure policy code derives final classification from that proposal, operator authorization, concrete execution compatibility checks, and image-check results. A scope category remains a model interpretation, not a mechanically proven fact.

Apply precedence in this order:

1. First enforce explicit operator repository authorization. An explicitly unauthorized repository is `out_of_scope` with `OUTSIDE_SCOPE_POLICY` without source admission. Technical source-admission failures (unsafe paths, sensitive files, digest mismatch, missing source), invalid input, failed model/inspection, invalid output, or uncertain inspection cleanup are `error`, null classification. No later action.
2. Unknown scope, insufficient issue information, multiple issues, or unresolved required source locations: `needs_input`, null classification.
3. Out-of-scope proposal under the supplied policy: `out_of_scope` with `OUTSIDE_SCOPE_POLICY`.
4. In-scope proposal with unknown requirements or unsupported/missing capabilities: `in_scope_not_supported` with concrete blockers. `REQUIREMENTS_UNRESOLVED` prevents a supported classification.
5. In-scope proposal with all requirements satisfied, a concrete compatible observer route and operator-owned bindings, and an accepted immutable image: `in_scope_supported`.

Trusted blocker codes initially include `LANGUAGE_UNSUPPORTED`, `EXECUTION_MODE_UNSUPPORTED`, `TARGET_DEPENDENCIES_UNSUPPORTED`, `BUILD_UNSUPPORTED`, `SERVICES_UNSUPPORTED`, `NETWORK_NOT_PERMITTED`, `PRIVILEGES_NOT_PERMITTED`, `REQUIREMENT_UNSUPPORTED`, `REQUIRED_INPUT_MISSING`, `OBSERVER_UNAVAILABLE`, `IMAGE_UNDETERMINED`, `NO_COMPATIBLE_IMAGE`, `IMAGE_NOT_PERMITTED`, `IMAGE_UNAVAILABLE`, `IMAGE_INCOMPATIBLE`.

Current routes remain the existing Python, Node, and Java disclosure observers. Encode their actual constraints in concrete compatibility functions, not a generic plugin registry or a list of capabilities with no implementation. Language and execution-mode enums alone are insufficient to admit a target. Without supplied, compatible operator-owned investigation bindings, return `REQUIRED_INPUT_MISSING`; intake does not invent controls, assertions, fixtures, or exception policy. This design adds flexible analysis and recommendations, not general test execution.

For example, a Python HTTP issue can receive `python:3.12-slim` only if that exact reference is in the supplied available-image inventory and its reviewed capabilities fit the proposed environment. It can still receive `SERVICES_UNSUPPORTED`/`OBSERVER_UNAVAILABLE` as blockers. If only callable observer images are available and none fits, return null with `NO_COMPATIBLE_IMAGE`, rather than suggesting an unavailable base image.

Before the model episode, trusted code inspects the operator-configured candidate image references through the Docker SDK and includes only locally present, operator-permitted, host-platform-compatible images in a bounded inventory. This is not a dump of all host images. Each entry contains a canonical selectable reference, immutable local image ID, and reviewed capability metadata from operator configuration, not target-authored labels. Record the inventory digest. A successful empty inventory is valid and forces a null recommendation; a Docker inventory failure is `error` with `IMAGE_CHECK_FAILED`, not an empty inventory. Do not implicitly pull, build, or contact a registry.

The agent must select an exact reference from that inventory or null. A generic base image is not interchangeable with a Corsair evidence observer image. Supported cases must select an available configured compatible observer image; there is no implicit substitution. Recheck the selected reference/immutable identity before accepting execution compatibility. Store the original recommendation and accepted immutable identity separately. The fixed inspection image is configured independently and is not automatically a candidate target image.

For an in-scope otherwise complete assessment, no suitable inventory entry produces `completed`, `in_scope_not_supported`, and `NO_COMPATIBLE_IMAGE`. If a selected entry disappears or its reference changes identity after inventory capture, return `IMAGE_UNAVAILABLE` or `IMAGE_INCOMPATIBLE` and an unsupported classification; do not substitute another image. A newly forbidden selection similarly produces a completed unsupported decision with its blocker. If rechecking fails operationally, return `error`, null classification, `IMAGE_CHECK_FAILED`, and retain the proposal. Do not turn unavailable infrastructure into a semantic support judgement. Execution compatibility may remain `image_check: not_checked` when existing semantic blockers already establish unsupported execution, but inventory membership is always validated, including for unsupported cases.

Frozen semantic evaluation supplies an explicit frozen available-image inventory rather than querying current host images. Production inventory discovery and identity rechecks have separate real-Docker tests. Resolving an image proves identity/availability, not that its declared tooling works; actual observer conformance remains a separate qualification gate.

## Execution and sandbox boundary

Add `IntakeWorkflow`, with ordinary activities for preparation, the ADK episode, image checks, and immutable recording. Pure classification can run in deterministic workflow code or the owning policy function; all filesystem, network, model, Docker, and storage operations stay in activities. Reuse Temporal deadlines/cancellation/retries and native ADK callback accounting; do not add an agent loop or repair broker.

Preparation fetches an issue when requested, captures the available-image inventory, and snapshots local source independently of `Case`/`Recipe`. Reuse `snapshot_source` and its no-follow, size, file, sensitive-file, and digest checks. Do not weaken admission to accept full arbitrary repositories; rejected snapshots remain explicit.

Use a fixed reviewed inspection image, separate from the suggested target image. A Docker-backed inspection session exposes only typed `list_files` and `read_file` operations bound to the immutable snapshot. Source is mounted read-only after trusted safe staging, with network disabled, non-root execution, read-only container filesystem, restricted capabilities, resource/time/output limits, and no credentials/socket inside. Implement fixed reader operations; no agent-provided shell fragments. Do not run source, imports, install hooks, Dockerfiles, repository tooling, or instructions found in files. Keep agent-private tools under `agents/intake/`; Docker mechanics stay under adapters.

The model episode receives the admitted issue content, operator scope policy, trusted available-image inventory, bounded source-reading tools, and packaged instructions. Credentials, host paths, raw artifact internals, private fixtures, and evaluator labels are excluded. Count all tool/model calls against an explicit intake budget; initially reuse existing budget ceilings through a separate intake settings field rather than the producer's runtime budget allocation.

Cleanup is bound to immutable container identity. Cancel/deadline paths perform and verify cleanup; lost/uncertain cleanup prevents supported classification. On retry, reconcile existing inspection ownership before creating another container. No exactly-once or host-loss continuation claim is added.

## Package ownership and interfaces

| Location | Work |
| --- | --- |
| `contracts/intake.py` | Canonical request, issue, proposal, result, enums, and invariants. |
| `agents/intake/` | Factory, metadata, instructions, contract re-exports, and private typed source tools. Add procedural guidance only if useful; no empty skill scaffolding. |
| `adapters/inference/adk.py` | Native fresh intake runner and usage/budget enforcement. |
| `adapters/scm/` | Concrete GitHub issue fetch plus recipe-independent source preparation. No remote checkout. |
| `adapters/sandboxing/` and `deploy/intake/` | Fixed inspection image, typed reader implementation, lifecycle and cleanup. |
| `policies/intake.py` | Pure classification and concrete compatibility decisions. |
| `steps/intake.py` | Fetch, snapshot, model episode, image check, and record activity composition. |
| `workflows/intake.py` | Bounded deterministic coordination. |
| `entrypoints/` | CLI/API intake submission and explicit worker registration. |
| `evaluation/intake.py` | Frozen input loading and deterministic external scorers. |

Extend only the relevant narrow ports with implemented operations; do not make the existing producer/auditor packets accept intake-only fields. Include role resources and inspection-reader implementation in configuration identity. Load packaged instructions from the installed wheel.

Proposed CLI surfaces are `corsair intake --json PATH --source PATH` and `corsair intake --issue OWNER/REPO#NUMBER --source PATH`. They submit the same typed request through the ordinary Temporal client. The CLI reads JSON locally and resolves explicit source arguments; issue JSON cannot override source settings. These commands are proposed, not available instructions. No automatic transition to investigation is included.

## Evaluation design

Keep frozen artifacts under the existing `evals/` categories. Implement scorers only in installed `evaluation/` code; `evals/evaluators/` describes them. Oracles never enter workflow/agent/tool inputs.

Use three input cohorts with the same production factory:

1. Raw JSON plus a frozen repository: combined normalization and analysis.
2. Canonical issue plus a frozen repository: analysis without normalization uncertainty.
3. Frozen GitHub response plus the same repository: adapter mapping and semantic equivalence with JSON. Live GitHub fetch conformance is separate from replayed response accuracy.

An oracle records accepted classification/surface/language/modes, required and permitted requirement/reason sets, accepted path/symbol pairs, and acceptable selections from the input's frozen available-image inventory (including null). No prose similarity or model judge is needed for primary scoring. Exact title/description checks apply to canonical and deterministic provider mappings; arbitrary prose normalization uses human-reviewed fidelity checks plus deterministic required location/field assertions. Do not claim enum matching fully measures summary faithfulness.

Image scoring uses exact membership in the supplied inventory and the oracle's acceptable subset; no substring matches, version guesses, or registry lookups. Out-of-inventory suggestions fail validation. Include paired cases for the same issue with a suitable image present, absent, and an empty inventory: the correct selection must change with availability. Pin inventory contents and capability metadata with the fixture hashes. Resolve neither tags nor labels during a frozen semantic repeat.

Report classification confusion matrix, per-class precision/recall, false-supported count/rate, enum field accuracy, requirement/reason precision/recall, location precision/recall, acceptable-image rate, null/abstention rate, operational failure rate, repeat agreement, usage, and latency. Set metrics ignore ordering/duplicates after validation. Invalid output, abstention, and provider failures stay in the full denominator; conditional semantic metrics show their denominator separately. Unknown cost remains unknown.

Include supported existing callable cases with operator bindings; HTTP services; Java/Maven; TypeScript builds; configuration-only issues; external databases; multiple-language repositories; unsupported languages; missing/malformed/multi-issue JSON; contradictory reports; missing source locations; misleading manifests; prompt injections; image policy blocks; unavailable Docker; and failed cleanup. Include same-language cases with different tooling needs so language-only image guessing cannot pass. Group equivalent issue variants and repository families into the same split to prevent leakage.

Before production qualification, human-review candidate cases, freeze human-labelled family-grouped held-out cohorts, and predeclare accuracy thresholds. Minimum mechanical gate: no invalid proposal can be admitted as supported; any false-supported held-out result blocks promotion pending review. Initial development scores remain diagnostics, not promoted accuracy claims.

## Implementation sequence and acceptance

1. Contracts, pure policy, concrete compatibility checks, frozen candidate cases, and scorer. Prove invariants and classification precedence with meaningful unit tests.
2. Fixed inspection image/session, recipe-independent snapshots, role factory/resources, and native ADK conformance. Test actual Docker isolation, bounded reads, cancellation, and immutable-ID cleanup.
3. Temporal activities/workflow, CLI/API/worker, artifact identity, and real GitHub issue adapter. Test finite HTTP failures without credential exposure; actual provider conformance separately.
4. Independent live intake cohorts, composed ADK/Docker/Temporal intake, and existing producer/auditor regression gates. Keep semantic accuracy, Docker isolation, Temporal replay, and live service checks distinct.
5. Update current guides/schema/CLI references, clean owned dead code, rerun affected tests and frozen evals, run `just check`, offline/native gates, `just build`, and verify installed resources outside the checkout. Record actual failed/unrun gates and exact configuration identity before any qualification claim.

This is a new component spanning contracts, source acquisition, a sandbox role, and durable coordination, rather than a prompt-only change. General agent-authored test plans, new evidence observers, target dependency installation, remote repository acquisition, and automatic investigation handoff are separate extensions.

## Design review and validation record

Design-only change on the existing `manus/just` working tree. Existing unrelated local modifications remain in place. An independent builder review identified binding authority, recommendation versus admitted image, classification precedence, and scoring claims. The design now specifies operator-attested bindings, explicit observer-image matching for supported routes, distinct authorization/technical failures, image-error mapping, and deterministic primary metrics rather than complete semantic scoring. Subsequent user direction restricts all recommendations to the supplied currently available-image inventory, with null/`NO_COMPATIBLE_IMAGE` when none fits and exact inventory-based evaluation. Security-only scope remains a proposed policy default for design approval.

Validation: the initial sandboxed `nix develop --command just check` could not access the external Nix cache. The approved retry passed Ruff lint, Ruff format (124 files already formatted), Just formatting, ty with warnings as errors, and local documentation checks. No runtime code was changed. Runtime, model, Docker, Temporal, and package qualification for intake are unrun because intake is not implemented.
