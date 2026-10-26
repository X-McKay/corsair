# Corsair pilot risk assessment

Owner: the Corsair maintainer. Execution class: durable; deployment tier: personal-use pilot, not production qualified. This assessment is included in the wheel and its digest is included in capability manifests.

The pilot accepts authorized source trees and operator-defined recipes, each with one fixed observer per runtime: Python callable secret disclosure and command sentinel, JavaScript prototype pollution, Ruby and Java secret disclosure, Perl HTML injection, and C integer overflow. Agents can read admitted source files and propose JSON payloads. They cannot author execution code, change fixed arguments, install dependencies, modify trusted tooling, choose a runtime, publish results, or close security findings.

Untrusted source and native target execution are confined to a dedicated disposable sandbox host. Docker uses an unprivileged user, dropped capabilities, no new privileges, network isolation, read-only source/driver/fixtures, and CPU/memory/process/time/output limits. These settings do not establish a universal malicious-code boundary. Prefer a qualified gVisor runtime or dedicated VM isolation when hostile source is admitted; do not share the host with secrets or production services.

Evidence risk: target code can be malicious, and every runtime's observer runs inside the target's own process or reads files the target process can also write, so hostile source can forge what the trusted driver reads. The observer is protected from model-written code by admitting only data payloads, but it is not attestation of an arbitrary hostile interpreter or binary. A target that detects the harness, edits its own process state, spawns uninstrumented descendants, or tampers with reporting requires a stronger observer recipe and must not be represented as universally verified. Runtime containment is independent of evidence authenticity.

Observer integrity per runtime, the documented boundary rather than hostile-source attestation:

- Python: pytest's result, coverage.py data and the observation file live in the target's interpreter and work directory.
- JavaScript: the `node:test` result, the V8 coverage directory and the observation file share the target's Node process and work directory.
- Ruby: Minitest and the built-in `Coverage` module share the target's interpreter.
- Java: the JUnit console launcher and the JaCoCo agent share the target's JVM.
- Perl: `Test::More` and the core line tracer share the target's interpreter.
- C: the AddressSanitizer report is read from stderr, which the target also writes, and the gcov counters are written by the target process. A C violation therefore also requires the run to end with the sanitizer's own halt status (`ASAN_EXITCODE`); report text from a target that returns normally, or that status without a target-bound report, is an operational error, never a violation. Hostile C source can still print the report and exit with that status, or write its own counters.

Semantic risk: an auditor can falsely accept or reject. Its review is outcome-blind, fresh-context, and constrained by schema. It cannot authorize a result without admitted source evidence. Independent human-labelled auditor cases and whole-system evaluations are required before production use. Shared producer/auditor models have correlated failures.

Failed reproduction never means not affected. Application exposure remains conditional when only a component API is exercised. Fix results mean the submitted demonstration is blocked while the benign control remains valid, not that all related vulnerabilities or regressions are resolved.

Operational risks: a lost local artifact host loses retrievability; Temporal does not snapshot it. Interrupted/unknown operations reconcile committed manifests and are not blindly re-executed. Cancellation must stop and remove owned containers before the activity completes. Credentials remain in the worker environment, never in source snapshots or workflow arguments. Model/tool/round/time limits are hard admission bounds; token counts and cost may be unknown and are not claimed as exact pre-call financial limits.

Production/team use, privileged capabilities, remote publication, arbitrary probes, new evidence types, and new languages require a new assessment, affected conformance tests, human review of residual risk, and new capability identities. No automatic external approval or risk acceptance is implemented.

Raw native evidence requires a non-empty image identity equal to the admitted manifest image. Missing or mismatched image identity invalidates evidence; this does not establish generic hostile-source observation integrity.

The control role must confirm physical container cleanup before admitting the adversarial role. Unconfirmed cleanup stops the operation and remains explicit uncertainty, never a negative security verdict.

The native producer schema permits an explicit no-grounded-candidate decision. It cannot create an observation, refute a finding, claim a fix, or authorize publication. The model/recipe combination remains unpromoted until its separate live fixture and composed evaluation gates qualify it.

Terminal JSON is limited to 1,000,000 bytes. Optional diagnostics are capped with an explicit marker and exception chains are bounded at transport boundaries. Factual evidence and operation claims are not shortened; oversized structured results fail explicitly and may have no committed final-result receipt, while referenced native artifacts remain retained.

The declared outer probe timeout is forwarded to the trusted controller instead of a hidden 120-second cap. Controller supervision, coverage collection limits, isolated execution and immutable-container cleanup remain separate boundaries; a longer configured timeout does not grant broader sandbox permissions.

## Native procedural skill loading

The role-local procedure configuration admits reviewed installed-package SKILL.md text and references, parsed by native ADK and preloaded into each role's instruction. No role has a skill loader: the producer has exactly its two bounded source readers, and the outcome-blind auditor declares no tools at all. No role receives a script runner, host code executor, environment, registry, remote skill discovery or additional network/source/target-execution permission. Always-on instructions and trusted evidence policy remain authoritative. All admitted skill resources contribute to manifest capability identity and the existing immutable execution intent binding.

This is a changed prompt/tool/configuration identity requiring independent frozen producer/auditor diagnostics, real native consumer tests and a distinct composed live gate. Loading a procedure is not evidence that its reasoning is correct, and does not promote model quality, negative clearance, host isolation or production readiness. Missing usage/cost and loader/provider errors remain explicit.

Required role procedures are loaded by the native ADK parser during controlled factory assembly and supplied as instruction text before generation. Usage.skills_preloaded and agent.skill_preloaded record that actual preparation. Neither role now has a loader, so Usage.skills_loaded is always empty and no procedure load is ever a claimed tool execution. This preload prompt identity supersedes the optional-loader-only diagnostic stage, whose zero-load results remain retained.

The producer's native SkillToolset is removed (a changed producer tool surface, prompt and capability identity). It re-offered the already preloaded, reference-free procedure, cost about 3.3 KB on every producer request through ADK's generic skill instruction and loader declarations, and that generic text told the model to load the skill first. The producer's `agent.json` declares empty `loader_tools` and `loader_call_limit` 0, and its Usage.skills_loaded stays empty; a model-invented loader call is a native unknown-tool error charged to the ordinary tool budget, not a load. The change narrows the producer's permissions and requires the same frozen producer diagnostics and composed live gate before qualification.

The auditor no longer receives the optional loaders (`agent.json` declares empty `tools` and `loader_tools`, `loader_call_limit` 0 and `llm_call_limit` 1). With no tools, native ADK sends the `AuditResult` response schema itself on every route instead of adding a `set_model_response` tool on routes without schema-with-tools support, and appends no generic skill-loading guidance, so one JSON-mode request completes a review and charges no tool call. A model that names a tool anyway is stopped by the zero tool budget before anything runs and returns a typed non-operational `audit_invalid`. This is a changed auditor prompt, capability and spec identity (`spec_digest`, `instruction_digest`, `tools`, `agent_resources_digest`; the skill bytes and `runtime_skills_digest` are unchanged) that requires a fresh frozen auditor diagnostic before its results are compared with earlier auditor rows.
