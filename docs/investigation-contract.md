# Investigation contract

An investigation validates one reported security hypothesis against an immutable source revision. It creates two tests, records their execution, and reports what that evidence establishes. It does not discover unrelated vulnerabilities, repair application code, or automatically close an issue.

## Inputs and identity

Required inputs are an issue snapshot, repository location, resolved commit, and authorized validation scope. An optional fixed commit enables comparative fix verification. GitHub issues and Azure DevOps work items map to the same issue snapshot; repository acquisition is separate from issue acquisition.

The snapshot records the issue title, relevant body and discussion, origin, retrieval time, and content digest. A moving branch is resolved to a commit before execution. Each source snapshot records its commit, content digest, acquisition result, and any admitted submodules. Submodules are independently pinned; incomplete acquisition blocks the affected path.

Issue text and repository instructions are task data. They cannot change tool authority, credentials, policy, budgets, or the graph.

## Supported scope

| Scope | What evidence can establish |
| --- | --- |
| Component | Behavior of the real target function or component under specified inputs |
| Application path | Behavior through a real route, middleware, or equivalent application entry point |
| Deployment | Behavior under the actual relevant deployment configuration and exposure |

The initial release qualifies component and selected application-path cases. The report always identifies which scope was exercised. Component exploit reproduction does not prove remote reachability. Component rejection does not prove that every application path is safe.

Initial qualification targets Python 3.12/pytest and Java 17/Maven/JUnit 5, for path traversal and bounded command-injection cases. Runtime, framework, platform, dependency access, and vulnerability class are checked separately. Findings needing unqualified concurrency, native instrumentation, external services, a different JDK, or deployment configuration return an explicit unsupported scope or requirement. A full source rewrite or changed production logic is never an acceptable setup workaround.

## Security hypothesis

The issue-analysis output identifies:

- Real entry point and source citations.
- Attacker-controlled input and attacker capabilities.
- Preconditions, configuration, and required dependencies.
- Suspected sensitive operation and observable security effect.
- Validation scope and what remains outside it.
- A hypothesis that can be supported or refuted by the planned observations.

Missing facts are recorded as missing. They are not silently invented to make a test executable.

## The two tests

Exactly two finding-specific tests are generated. Infrastructure qualification fixtures and evaluator checks are separate from these two tests.

| Test | Contract |
| --- | --- |
| Control | Benign input through the relevant real path; required behavior succeeds on vulnerable and corrected revisions |
| Security regression | Reported adversarial condition through the real path; asserts required safe behavior, so a vulnerable revision fails the security assertion and a corrected revision passes |

The test plan names fixtures, actual implementation calls, expected behavior, observable effects, discovery commands, and scope limitations. Tests must not mock out the sensitive behavior, assert a constant, reproduce a substitute implementation, or treat arbitrary exceptions as rejection.

For path traversal, an allowed file supplies the benign control and a synthetic file outside the application's allowed directory supplies the security observation. Both files remain within the operator-authorized sandbox fixture area. For command injection, use a bounded synthetic effect such as a marker in scratch space; never depend on a real external target.

The source snapshot remains immutable. Test changes are an explicit patch restricted to approved test paths. Native test/build configurations are preserved. Where adding tests requires an unsupported configuration change, report that limitation rather than modifying application behavior.

## Test validity and execution validity

Test validity and execution validity are evaluated separately. Evidence of test validity includes source linkage, correct assertions, relevant path execution, and expected behavior on reviewed vulnerable/fixed fixtures. Where supported, capture a specific observable witness of path execution or effect. Do not infer path coverage from an exit code alone.

Execution validity requires native test discovery, an actual run rather than stale results, individual test outcomes, complete command delivery, and sufficient retained evidence. Compile errors, skipped tests, dependency failures, failed fixtures, incomplete logs, and timeouts are not security observations.

An agent-authored assertion or JUnit report is evidence of a test claim, not independent semantic attestation. Repository runners and plugins are untrusted. Fresh execution and integrity checks improve reproducibility but do not establish that a test measures the correct property. Use reviewed cases, explicit witnesses, and analyst review where automated validation cannot resolve that question.

## Sandbox interference

Record the application observation separately from the sandbox observation. A boundary denial can prevent an effect while the application remains vulnerable. It cannot establish that the application rejected the input correctly or that a fix succeeded.

Prefer synthetic fixtures accessible within the approved boundary. If the sandbox prevents the required observation, return blocked or inconclusive with the denial evidence. Do not broaden authority or reinterpret a policy denial as application safety. Resource limits can also prevent timing or memory observations; disclose that interference.

## Conclusions

Reports carry independent fields:

| Field | Values |
| --- | --- |
| Execution | completed, blocked, failed, unknown, unsupported |
| Finding | reproduced, not_reproduced, refuted_in_scope, inconclusive |
| Fix | verified, not_verified, not_applicable |

`not_reproduced` means the tested attempt did not demonstrate the reported effect. `refuted_in_scope` requires affirmative evidence explaining why the reported condition cannot occur under the stated assumptions. Failure to reproduce alone is insufficient.

`fix: verified` requires the same frozen test patch, valid security assertions, passing controls on both revisions, a security assertion failure on the vulnerable baseline, and a security test pass on the fixed revision. Both environments and any differences are recorded. If the tests cannot execute comparably on both revisions, report partial evidence and `not_verified`.

Operationally incomplete runs normally yield `inconclusive`. If earlier valid evidence already reproduced the finding, preserve that observation while recording the incomplete run; it still cannot verify the fix. Contrary valid observations block a conclusive disposition until the contradiction is explicitly resolved in a new evidence attempt.

## Report contents

Markdown and machine-readable reports include inputs and identities; support and validation scope; hypothesis and preconditions; environment and boundary identities; frozen tests and commands; per-revision results; application and sandbox observations; source citations; failure details; disposition and limitations; performance summary; and cleanup status. Include authorized artifact references and digests for reproduction.

The evidence-assessment agent proposes an interpretation. Deterministic gates admit or reject its proposed disposition. InfoSec retains issue closure authority. Report publication and issue modification are outside the initial workflow.
