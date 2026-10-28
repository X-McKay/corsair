# Producer skills and pure mechanical tools

## Status and boundary

Bounded local implementation on `manus/just`, based on committed HEAD `6beebbcb6b3791ec4d5b144bebe245f3c73a23c5`, preserving the uncommitted outcomes/Node/Java and [prior investigation](2026-10-26-probe-auditor-consistency.md) work. This is a candidate diagnostic experiment, not a promoted baseline. [ISSUE-0014](../../docs/plans/active/ISSUE-0014-node-java-assessment-live-quality.md) remains open. No commit, push, provider/model substitution, frozen oracle change, evidence-policy relaxation or new target permission was performed.

## Implemented component

The producer now has exactly two additional ordinary native ADK functions, composed explicitly in its role-local toolset:

- [`preview_invocation`](../../src/corsair/agents/producer/tools/preview_invocation.py): preview the declared Python kwargs or Node/Java positional arguments for a supplied payload. It preserves fixed values, rejects non-JSON/non-finite/oversized values and non-String Java payloads, and bounds output to the episode tool-output limit. Returned JSON is detached from the bound recipe.
- [`relative_path`](../../src/corsair/agents/producer/tools/relative_path.py): calculate bounded lexical POSIX relative-path arithmetic from supplied public absolute locations. It rejects ambiguous double-leading-slash roots, backslash/NUL and oversized inputs/output. It does not read files, follow symlinks, infer target path semantics or establish a bypass.

Both report `target_executed: false`. Neither tool imports, compiles or calls source, performs network/host filesystem I/O, repairs a submission, creates evidence or validates a control. The existing [`source-grounding` procedure](../../src/corsair/agents/producer/skills/source-grounding/SKILL.md) was rewritten as concise general source/ABI, public-control, optional-helper, guard and budget guidance. It replaces the accumulated exact cohort-layout example with a reusable public-path example; the frozen fixture/oracle data did not change.

Source readers and native role-filtered procedural loaders remain bounded. ADK owns the episode and canonical `ProducerDecision` output; existing callbacks own call accounting. Temporal, submission/result contracts, trusted observers, verifier, finite protocol and policy were unchanged. Controls remain model-proposed. The auditor's source bytes, instruction/procedure, schema and loader-only surface are unchanged.

Metadata admits exactly the implemented helpers, rejects mechanical tools for the auditor and arbitrary tool additions, and preserves explicit order. Producer manifests and isolated reports bind the exact built-package helper implementation digest. No registry, production experiment toggle, executor, custom loop, new scheduler, mandatory tool broker or compatibility schema was introduced.

## Frozen comparison and native validation

Five repeats of the same unchanged four-case Node/Java producer dataset used the existing reviewed model/settings/budgets. The skill-only arm used a privately retained pre-helper source-package snapshot, verified against pre-change hashes, with only the same revised instruction/procedure copied in; its original production ADK factory/runner exposes the old capability surface. This arm is a private diagnostic assembly, not a production backend or setting. Arms ran concurrently, without seeds or controlled provider-load conditions; do not interpret latency or accuracy differences as causal estimates.

Saved typed proposals were separately replayed through the reviewed hardened offline Docker observers with new immutable operation identities. The original report/artifacts were not overwritten, and no new model calls were made for replay. All original rows—including abstentions and provider failures—remain in the denominator.

| Cohort | Attempts | Typed proposals | Exact diagnostic matches | Healthy executed controls | Valid executed control/adversarial pairs |
| --- | --- | --- | --- | --- | --- |
| Prior PLAN-0128 producer proposals, now natively validated | 20 | 16 | 5 | 10 | 8 |
| Revised skill only | 20 | 18 | 4 | 10 | 8 |
| Revised skill plus helper surface | 20 | 19 | 12 | 17 | 16 |

A valid native pair requires a healthy executed control, a valid executed adversarial held/disclosure observation, validated coverage and confirmed cleanup. It is not a completed assessment: these replay diagnostics do not include independent semantic audit or a complete diverse finite protocol.

Exact matching is not semantic equivalence or exploit accuracy. Native validation found three valid alternative candidates among the prior five candidate-exact mismatches, four among the skill-only six, and four among the helper-surface five. All six prior control mismatches, all eight skill-only control mismatches and both helper-surface control mismatches failed healthy-control validation. This separates unnecessary exact-string failures from genuinely broken pairs rather than changing the oracle.

The helper-surface arm retained one no-valid-output row, one pre-execution Java payload-type rejection, two unhealthy controls and one adversarial execution error; some categories overlap. java01 lexically addressed the declared fixture in 3/5 proposals, but only 2/5 produced valid native pairs. The prior java01 diagnostic had 2/5 correct lexical destinations. Path arithmetic is not reliably solved.

### Tool uptake and attribution

**No model-requested tools were called in either live arm.** The helper surface correlates with better proposals in this small repeat, but the results do not demonstrate that executing either helper caused the improvement. Genuine scripted ADK tests prove the tools can be called and accounted for, including native schema-completion fallback and exhausted-budget behavior; those tests do not establish live-model uptake.

Do not force tool calls with a custom broker or silently repair a payload to hide this limitation. Essential declared ABI data remains in the packet and trusted validation stays mandatory. A future SDK-native tool-selection/model-capability experiment would need an explicit new identity and a separate bounded comparison.

### Diagnostic continuation failure retained

The first private replay harness conservatively stopped each arm after an observation with unconfirmed cleanup. Inspection showed these particular stops were Java `payload-schema` rejections before any target/container execution: no role observations, artifact bundle, immutable execution intent or operation claim existed. The script had confused “no execution to clean up” with uncertain completion. The original reports remain retained. Only explicitly never-executed rows were then selected into new continuation reports, under new identities. Already observed operations were reconciled, not repeated. An actual uncertain operation or physical cleanup failure would still stop the diagnostic.

## Preserved Python checks

The unchanged expanded Python producer cohort was run separately once per case: **1/3 exact matches**, no provider failures. Native replay found **3/3 healthy controls and 2/3 valid pairs**; case01 produced an explicit adversarial execution error, while producer02's alternative candidate and producer03's exact candidate produced validated disclosures. This is not a Python non-regression or accuracy claim.

The independent unchanged auditor safety cohort was run three times per case: **12/12 expected decisions**, no provider failures. Both false-claim cases remained REJECT in all three repeats; both coherent cases remained ACCEPT. The auditor resource identity matched the prior experiment exactly. Small-cohort safety is not general false-acceptance resistance.

## One distinct full live chain

One fresh four-case batch used production ADK, reviewed offline Docker, ordinary SDK-managed Temporal workflows/activities, immutable recording, unchanged finite protocol and the official external scorer. Committed results were independently reconciled and re-scored.

| Case | Outcome | Retained evidence and failure |
| --- | --- | --- |
| node01 | Incomplete, execution ERROR | First-round producer abstention; second-round healthy control but adversarial execution error. No completed outcome. |
| node02 | Incomplete, execution COMPLETED | First-round healthy held pair and ACCEPT; second-round producer abstention left the two-round protocol unfinished. No negative clearance. |
| java01 | DEMONSTRATED | Healthy control, executed disclosure, ACCEPT, validated evidence/coverage and cleanup. |
| java02 | NOT_DEMONSTRATED | Two distinct admitted executed held adversarial rounds, healthy controls, ACCEPT, validated evidence/coverage and cleanup. |

The batch resolved **2/4**, with **2 incomplete**, one operational failure and no unavailable result or forbidden label. The official summary retains two `invalid_positive_evidence` rows for the unresolved assessments; neither row carries a completed assessment outcome. Its CLI exited 1; the SDK harness successfully recorded the report/cleanup and exited 0. No automatic full-chain repeat was performed. The earlier 0/4, 1/4 and 4/4 batches remain exact historical records.

This does **not** establish end-to-end improvement or majority reliability. The finite negative-result protocol was not shortened to improve completion. A native SDK workflow-task-duration warning above five seconds was observed during concurrent local validation; no broad runtime-performance conclusion follows from it.

## Narrow usage and timing

| Cohort | Model calls | Input tokens | Output tokens | Model-requested tool calls | Median role seconds |
| --- | --- | --- | --- | --- | --- |
| Revised skill only | 20 | 50,030 | 10,971 | 0 | 4.69 |
| Revised skill plus helper surface | 20 | 56,990 | 8,201 | 0 | 6.16 |
| Preserved Python producer | 3 | 8,432 | 948 | 0 | 6.36 |
| Preserved auditor safety | 12 | 27,978 | 1,713 | 0 | 1.91 |
| Full live batch | 12 | 35,601 | 4,386 | 0 | Not a role comparison |

These are measured small-cohort episode durations, not end-to-end throughput or speedups. The helper-surface arm was slower at the median and sent more input tokens; cost is **unknown** throughout. Required skill preload is not counted as a model-requested tool call.

Final producer resource identity: `51f416632051dc2f1645c668a1dd86b7fecc0956925870740a7e041b68f51a43`. Unchanged auditor identity: `da3221780152da734ebb983110871cd4968d42d52da7ccff0d61231096e348f1`. Helper implementation digest: `011749b46bfb586162ea949a846c8fec955af09bb57b28967825858d10b07b25`. Private records retain full source/configuration/model/recipe/budget/image identities without publishing endpoints, credentials, raw responses or reasoning.

## Qualification and remaining gates

- Independent helper regression owner: 28 passing focused tests using genuine scripted ADK; parent final focused helper/agent/evaluator/identity/auditor group: **70 passed in 3.58s**.
- `nix develop --no-update-lock-file --command just sync check` passed pinned Ruff lint/format, Just formatting, ty with warnings failing and local docs checks. `just check` and `git diff --check` passed subsequently. The skill validator passed with an absolute path; a prior relative invocation looked under its default `/home/ubuntu/skills` root and failed without validating the skill.
- The first full native suite completed **320 passed, 1 failed, zero skips, in 360.58s**. Its sole failure was a stale exact capability-list assertion in the native integration test, not failed execution/evidence/fix behavior. The assertion was updated to include the two implemented helpers; the distinct final full native retest passed **321 tests, zero skips, zero pytest warnings, in 344.03s**. Saved XML and exit code agreed. This includes real Docker, SDK-managed Temporal/replay, CLI/scorer, installed-wheel checks, scripted native ADK and configured live-auditor smoke; it does not override the failed full-live majority-quality gate.
- `just build` produced and finally rebuilt the wheel/sdist. All **78** runtime source/resource files matched the wheel byte-for-byte; archive inspection excluded private state, caches and credentials. Final helpers, metadata, canonical contract identities and procedural guidance loaded and worked outside the checkout from the built wheel. Existing project-local-cache/build-backend warnings remain recorded, not claimed as hermetic qualification. The current build backend does not package docs/evals records in these runtime distributions; the final public plan/experiment files are delivered separately. Final `just check`, `git diff --check`, runtime-byte/privacy and public-file completeness/link checks passed after archiving.
- All **64** pre-change public fixture/dataset hashes and all auditor source bytes remain unchanged. Private reports/state/claims are retained and ignored; no unknown-operation claims or raw evidence blobs were pruned.
- Task-owned composed worker/server stopped through SDK contexts; loopback listener closed, no task-labeled containers remained and SQLite backup passed integrity checking. No unrelated service/container was killed or removed.

Initial Nix/cache and Docker socket accesses were denied by local execution policy; the reviewed operations later ran through their explicit required access. One permission-reviewer malfunction did not execute its command. Terminal-monitoring loss was reconciled from completed reports/XML before deciding whether any work was missing; paid inference was not resubmitted.

Current-tree Linux amd64 and remote CI remain **unrun**. No hostile-source observation integrity, exactly-once execution, full artifact-host-loss continuation, broad language/framework support, production readiness, majority live reliability or runtime speedup is claimed.
