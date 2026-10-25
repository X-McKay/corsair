# Corsair pilot risk assessment

Owner: the Corsair maintainer. Execution class: durable; deployment tier: personal-use pilot, not production qualified. This assessment is included in the wheel and its digest is included in capability manifests.

The pilot accepts authorized source trees and one operator-defined Python callable secret-disclosure recipe. Agents can read admitted source files and propose JSON payloads. They cannot author execution code, change fixed arguments, install dependencies, modify trusted tooling, choose a runtime, publish results, or close security findings.

Untrusted source and native target execution are confined to a dedicated disposable sandbox host. Docker uses an unprivileged user, dropped capabilities, no new privileges, network isolation, read-only source/driver/fixtures, and CPU/memory/process/time/output limits. These settings do not establish a universal malicious-code boundary. Prefer a qualified gVisor runtime or dedicated VM isolation when hostile source is admitted; do not share the host with secrets or production services.

Evidence risk: target code can be malicious and can interfere with an in-process Python test/coverage mechanism. The observer is protected from model-written code by admitting only data payloads, but it is not attestation of an arbitrary hostile Python interpreter. A target that detects the harness, edits its own process state, spawns uninstrumented descendants, or tampers with reporting requires a stronger observer recipe and must not be represented as universally verified. Runtime containment is independent of evidence authenticity.

Semantic risk: an auditor can falsely accept or reject. Its review is outcome-blind, fresh-context, and constrained by schema. It cannot authorize a result without admitted source evidence. Independent human-labelled auditor cases and whole-system evaluations are required before production use. Shared producer/auditor models have correlated failures.

Failed reproduction never means not affected. Application exposure remains conditional when only a component API is exercised. Fix results mean the submitted demonstration is blocked while the benign control remains valid, not that all related vulnerabilities or regressions are resolved.

Operational risks: a lost local artifact host loses retrievability; Temporal does not snapshot it. Interrupted/unknown operations reconcile committed manifests and are not blindly re-executed. Cancellation must stop and remove owned containers before the activity completes. Credentials remain in the worker environment, never in source snapshots or workflow arguments. Model/tool/round/time limits are hard admission bounds; token counts and cost may be unknown and are not claimed as exact pre-call financial limits.

Production/team use, privileged capabilities, remote publication, arbitrary probes, new evidence types, and new languages require a new assessment, affected conformance tests, human review of residual risk, and new capability identities. No automatic external approval or risk acceptance is implemented.

## This capability policy revision

The native producer schema permits an explicit no-grounded-candidate decision. It cannot create an observation, refute a finding, claim a fix, or authorize publication. The model/recipe combination remains unpromoted until its separate live fixture and composed evaluation gates qualify it.
