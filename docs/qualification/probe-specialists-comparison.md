# Independent probe specialists comparison

Measured on 2026-10-13 using the configured self-hosted Qwen3.6-35B-A3B-NVFP4 provider. This report concerns eval-only probe authors, not campaign disposition or production qualification.

## Design and scope

Compare a joint author with distinct independent control/exploit authors. Each specialist has a narrow role input, separate native Agent/context, dedicated skill, restricted single-file ownership and its own budget. Neither sees the other's artifact or reasoning. Joint gets the exact instruction/skill union, both files and the sum of allowances. Model requests are sequential; launch order rotates across role permutations. Both paths require actual source reads covering frozen anchors before admitting drafts.

Per specialist:20 model requests,20 tool calls,128000 tokens,900 seconds and2 output retries. Joint:40/40/256000/1800 and4 output retries. Provider settings are unchanged from the earlier pilot. Native outcomes and operator labels never enter drafting inputs.

Four synthetic property cases each supply two source revisions: SQL disclosure through in-memory SQLite; file disclosure through a controlled temporary filesystem; sensitive data in returned output; unauthorized state mutation before denial. Controls establish ordinary execution and expected behavior. Exploits assert the reported safety property using normal unit-test facilities. Mocks/fakes/fixtures are appropriate according to the observed property; these samples impose no universal real-dependency requirement. SQL engine behavior is scoped to SQLite; filesystem, output and mutation claims stay within their controlled fixtures.

One repeat on each visible-source case gives8 control,8 exploit and8 joint runs. This is four related revision pairs, not eight independent domains. It does not establish consistency, broad language/framework/CWE transfer or production performance.

## Original results

All24 live drafts completed within budget. Independent source-only reviewers inspected artifacts without execution outcomes, binding approved patches and complete source inventories. Each specialist was assessed with a frozen reference counterpart; assembled independent pairs were assessed separately. Invalid pairs did not run.

| Measure | Joint author | Independent authors |
| --- | ---: | ---: |
| Valid reviewed and executed pairs | 7/8 | 7/8 |
| Model requests | 55 | 64 |
| Tool calls | 47 | 47 |
| Input/output tokens | 215306 | 177928 |
| Sequential drafting seconds | 182.7 | 263.4 |

The control specialist independently validated7/8 probes; exploit validated8/8. The same public-profile case failed in both approaches because control asserted password-hash absence, thereby requiring the security fix. This was caught before execution. Three invalid pair configurations represent this defect in joint, isolated-control and assembled-independent views; they are not three independent agent failures.

29 supported pair configurations ran both probes on both revisions:58 revision runs,116 native probe outcomes, all matching the intended scoped behavior and all container cleanups confirmed. The four separately reviewed reference pairs also passed their calibration: control passed both revisions, exploit failed reported and passed fixed.

Independent authors used17.4% fewer tokens but16.4% more requests and44.2% more sequential drafting time. Concurrent specialist latency was not measured; do not report estimated parallel speed as an observed benefit.

## Source-only feedback and retest

Preserving the original scores, give each failed author one fresh correction task containing its previous artifact and the pre-execution source-review finding. No native/security outcomes were returned. The independent control had single-file authority; the joint author was asked to preserve its supported exploit bytes, which it did.

Both corrected pairs passed fresh independent source review and native execution on both revisions. Control passed both, exploit failed reported and passed fixed; cleanup confirmed. Counting those separately measured replacements gives8/8 for both designs after one correction. It does not replace the original7/8 score or establish a general repair success rate.

Control correction:6 requests,24.1 seconds,19818 tokens. Joint correction:5 requests,16.0 seconds,18834 tokens. This one retry showed no efficiency advantage for splitting; isolation did ensure that specialist repair could not change the exploit.

## Current recommendation

The joint author with explicit role guidance and bounded source-only feedback is the simpler current default: measured quality tied, with fewer requests and lower sequential latency. Retain the independent specialists and their isolated evaluations as the experimental path for targeted improvement and a future measured parallel comparison. Their lower token footprint and strict repair ownership are useful properties, but this run did not demonstrate greater correctness.

No measured coordination failure calls for DynamicWorkflow yet. Improve role-specific instructions and frozen cases using attributable findings; do not add orchestration to resolve control semantics. Broader repeats, negative/unsupported seams and language/framework transfers are needed before a production routing change or baseline promotion. The existing semantic-validity-review blocker remains separate: this experiment did not qualify that production reviewer.

## Validation and retained evidence

Nine focused agent/harness tests passed before launch. Four source-reviewed reference pairs ran successfully through the existing restricted offline Docker/native-runner adapters. Closing affected agent/harness/record selection passed14 tests in1.62seconds; diff whitespace check clean. Native usage fields were present for all24 primary runs and both corrections. Earlier restricted async test hangs and the historical shared-budget pilots remain recorded in PLAN-0093; their scores are not rewritten.

Ignored `.runs/probe-specialists/` retains frozen-live-v1 source/configuration, native message receipts, reference review/calibration,32 blinded pair reviews, complete native reports, scorecard-v1.json and separately versioned source-feedback/review/native evidence. No raw evidence is published. The optional-feedback evaluator extension and required explicit role-property projection were added after the frozen main run; original inputs remain exactly those retained in frozen-live-v1. The projection tightening changes no measured input because every measured caller already passed explicit role behavior.
