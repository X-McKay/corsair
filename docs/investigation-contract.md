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

The issue-identification stage preserves the reported concern and locates the relevant implementation with source evidence, or records a concrete blocker. It does not establish whether the issue occurs. Under [SPEC-0024](development/specs/SPEC-0024-issue-identification.md), the test-planning stage develops the conditional security hypothesis using that handoff, source reads and admitted environment evidence. The investigation must still establish:

- Real entry point and source citations.
- Attacker-controlled input and attacker capabilities.
- Preconditions, configuration, and required dependencies.
- Suspected sensitive operation and observable security effect.
- Validation scope and what remains outside it.
- A hypothesis that can be supported or refuted by the planned observations.

Missing facts are recorded as missing. They are not silently invented to make a test executable.

## The two tests

Exactly two finding-specific tests are generated and must execute as native tests on each investigated revision: the **control probe** and the **exploit probe** (security safety regression). Both call the real application path: the control supplies benign input and the exploit supplies the reported adversarial condition. The exploit probe asserts required safe behavior, so an unsafe implementation fails that assertion. Discovery, authoring or a model statement alone does not establish either probe executed. Independent validity review covers both calls and their assertions; native per-test outcomes establish execution. A missing, skipped, errored or unknown probe makes the evidence unusable, and a failed control cannot support a security verdict. Infrastructure qualification fixtures and evaluator checks are separate from these two tests.

| Test | Contract |
| --- | --- |
| Control | Benign input through the relevant real path; required behavior succeeds on vulnerable and corrected revisions |
| Security regression | Reported adversarial condition through the real path; asserts required safe behavior, so a vulnerable revision fails the security assertion and a corrected revision passes |

Unit tests are the default across languages, frameworks and CWEs. The shared contracts describe properties and observations rather than enumerating vulnerability classes; do not introduce per-CWE or per-language recorder requirements. Use the application's existing test seams and native framework to call the real target with controlled inputs and assert outputs, specific exceptions, fixture state, or interactions with controlled dependencies. The test plan names the source target, seam, fixtures, inputs, assertions, discovery commands, and limits of the property measured. Integration tests are needed only when the reported property depends on behavior beyond that seam.

A dependency double may record arguments or supply controlled responses through an existing seam. It must preserve the production logic responsible for the security property: never replace that logic with a substitute implementation, assert a constant, or treat arbitrary exceptions as rejection. For SQL query construction, call the real query-building function with a recording database double; check the benign query and parameters, then that adversarial input remains a bound parameter without changing query structure. This establishes query construction at component scope. Database-engine behavior needs separate integration evidence when relevant.

For path traversal, use allowed and outside-directory synthetic files within the operator-authorized fixture area, or a controlled filesystem dependency when the property is path validation before access. For command construction, a recording process dependency can establish the arguments passed to the real execution seam; actual shell interpretation requires a bounded synthetic integration effect. State which property each test establishes.

The source snapshot remains immutable. Test changes are an explicit patch restricted to approved test paths. Native test/build configurations are preserved. Where adding tests requires an unsupported configuration change, report that limitation rather than modifying application behavior.

## Test validity and execution validity

Test validity and execution validity are evaluated separately. After authoring freezes the patch and before investigation execution, a fresh call of the existing evidence-assessment agent reviews the reported condition, plan, tests and per-revision source. Its input excludes receipts, JUnit, verdicts and execution outcomes. Trusted code binds the review to the exact source and frozen observation plan/test patch; the later result assessment consumes that review and cannot rewrite it. The authoring agent cannot attest to its own validity. This separation reduces outcome bias; semantic review remains model judgment, not formal proof or independent runtime attestation.

The review must establish that both probes call the intended real implementation, exercise the benign/adversarial conditions, assert relevant properties and confine doubles to dependencies. Copies of the target, mocked targets, vacuous assertions and doubles implementing the security guard invalidate the relevant claim. Review all test code, the plan and reported condition, then use the evidence tool to inspect relevant source and helpers. Missing necessary source prevents affirmative review; bounded excerpts cannot certify omitted behavior. A passing control alone does not establish that an observation can detect the security defect. Use reviewed vulnerable/fixed examples to calibrate sensitivity where available. Matching observation kinds and a baseline/candidate differential are not sufficient proof of calibration or source linkage. Different observation kinds can be valid, such as a normal return for benign input and a specific rejection exception for adversarial input. Unresolved semantic validity remains inconclusive without imposing a new low-level recorder requirement.

A witness is optional supporting evidence of an application observation. Inputs, return values, specific exceptions, fixture state and recorded dependency interactions are valid unit-test observation boundaries. Missing low-level filesystem, process or database telemetry does not by itself invalidate a sound unit test. Use additional instrumentation only when the property needs it, preserve application semantics, and qualify its coverage. An empty recorder trace cannot prove absence beyond its admitted coverage. Do not require a new language-specific recorder to admit an existing native test seam, or infer path coverage from an exit code alone.

Execution validity requires native test discovery, an actual run rather than stale results, individual test outcomes, complete command delivery, and sufficient retained evidence. Compile errors, skipped tests, dependency failures, failed fixtures, incomplete logs, and timeouts are not security observations.

An agent-authored assertion or JUnit report is evidence of a test claim, not independent semantic attestation. Repository runners and plugins are untrusted. Fresh execution and integrity checks improve reproducibility but do not establish that a test measures the correct property. Use source-grounded validity checks, reviewed cases, optional supporting witnesses, and analyst review where automated validation cannot resolve that question.

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

`not_reproduced` requires a valid control and a valid security test establishing the planned safe property within the stated scope; it means the tested attempt did not demonstrate the reported effect. `refuted_in_scope` requires affirmative evidence explaining why the reported condition cannot occur under the stated assumptions. Failure to reproduce alone is insufficient.

`fix: verified` requires the same frozen test patch, valid security assertions, passing controls on both revisions, a security assertion failure on the vulnerable baseline, and a security test pass on the fixed revision. Both environments and any differences are recorded. If the tests cannot execute comparably on both revisions, report partial evidence and `not_verified`.

Operationally incomplete runs normally yield `inconclusive`. If earlier valid evidence already reproduced the finding, preserve that observation while recording the incomplete run; it still cannot verify the fix. Contrary valid observations block a conclusive disposition until the contradiction is explicitly resolved in a new evidence attempt.

## Report contents

Markdown and machine-readable reports include inputs and identities; support and validation scope; hypothesis and preconditions; environment and boundary identities; frozen tests and commands; per-revision results; application and sandbox observations; source citations; failure details; disposition and limitations; performance summary; and cleanup status. Include authorized artifact references and digests for reproduction.

The evidence-assessment agent proposes an interpretation. Deterministic gates admit or reject its proposed disposition. InfoSec retains issue closure authority. Report publication and issue modification are outside the initial workflow.
