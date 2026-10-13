# Corpus baseline and iterative improvement loop

This is the repository-owned procedure for establishing per-language disposition accuracy and improving it through bounded Docker evaluation. Start from any checkout of main; no Codex-specific worktree, local conversation or private artifact is required to understand the procedure. Track implementation in [PLAN-0087](../development/plans/PLAN-0087-corpus-baseline-loop.md); [HANDOFF-0113](../development/handoffs/HANDOFF-0113-repository-corpus-loop.md) supplies the fresh-session kickoff.

Use the existing [evaluation contract](../evaluation-and-acceptance.md), [investigation contract](../investigation-contract.md), [development workflow](../development/README.md) and native agent/runner ports. Keep exactly two finding-specific tests, evaluator-only labels, explicit runtime support and attributable evidence. This is a bounded workflow, not a new scheduler or an installed automation.

Publication base: main `e84a2bb`. That source has isolated `make eval` commands, corpus loading/materialization and the Docker product route, but not the local candidate’s finite corpus campaign module or Node22 readiness changes. Candidate-free product runs still refuse admission. These are dependencies to inspect/integrate or implement, not capabilities created by this document. Historical local pilots found an approved-directory/exact-file mismatch and planning output exhaustion; reproduce against current source before treating either as an active defect. No per-language accuracy baseline is established by this documentation.

## Baseline scope and scorecard

Freeze the existing development split first. A paired topic contributes one positive investigation with a candidate fix and one independent negative investigation with no candidate. An unpaired topic contributes one baseline-only investigation. Counts are configurations, not independent samples or repeat attempts.

| Language | Development topics | Development investigations | Held-out investigations |
| --- | ---: | ---: | ---: |
| Python | 17 | 32 | 10 |
| JavaScript | 7 | 14 | 4 |
| Perl | 5 | 10 | 2 |
| Java | 3 | 6 | 0 |
| C | 2 | 4 | 0 |
| Total | 34 | 66 | 16 |

The full corpus is 42 topics / 82 configurations. Preserve the current split manifest. Java and C have no existing held-out topics: their development results cannot establish unseen-family generalization. Keep original topic families together when admitting additional cases, including all variants, paraphrases and derived stage replays.

For each language and frozen candidate, report counts before percentages:

- Inventory coverage: account for every frozen configuration, showing attempt state (unstarted, returned with final record, or uncertain delivery) separately from support state (ready, unsupported or preflight-blocked), so blocked attempts are not double-counted. Separately show oracle-reviewed versus provisional/unresolved cases. A campaign slot marked completed only means its invocation returned; it does not mean an admitted final disposition exists.
- Decisive coverage: admitted, decisive finding dispositions divided by all frozen configurations. Unsupported, error, inconclusive and unstarted cases stay in this denominator.
- Useful accuracy: correct, evidence-supported decisive dispositions divided by all oracle-reviewed configurations in the frozen cohort. Failed, abstaining and unstarted reviewed configurations contribute no success. Report reviewed count / total alongside this score; unresolved oracles are never silently dropped to improve it.
- Conditional accuracy: correct evidence-supported decisive dispositions / all decisive dispositions on oracle-reviewed configurations. A zero denominator is N/A. Show false positives, false negatives, false fix verification and unsupported conclusions explicitly.
- Finding, fix and evidence validity separately, plus exact execution/finding/fix/scope agreement. A correct-looking label with invalid evidence is not a success. Reviewed indeterminate cases test appropriate abstention separately; they do not inflate decisive accuracy.
- First failure by stage and failure layer; language/framework, CWE, required effect and topic/family; latency, model/tool calls, retries, token coverage and cleanup status. Downstream stages not reached are not downstream agent failures. Missing telemetry remains unknown.

Use one predeclared primary attempt per configuration for breadth. Report all diagnosed reruns and deliberate repeats separately, with their source identity and predecessor. Topic-weighted and attempt-weighted results must not let repeated success on one topic masquerade as coverage. Small counts and correlated positive/negative variants preclude strong population-accuracy claims.

Before calling agreement accuracy, independently review the evaluator-owned expectation against pinned source and trusted native oracle evidence. Record reviewer/method, oracle version, scope, limitations and artifact references. Agent-generated tests or a model majority are not their own ground truth. Keep upstream labels as provisional hypotheses until this review; preserve ambiguous cases and disagreements explicitly. Verification tests, labels and variant identities remain outside all agent-visible inputs.

## First three bounded cycles

**Cycle 1 — obtain complete product dispositions and freeze a baseline.**

1. Reproduce the environment-approved directory versus planner/author exact-file mismatch in isolation. Decide one narrow contract, exercise all affected consumers, and compare frozen environment/planning/authoring evaluations. Retain the separate planning output-length failure; do not assume a path fix resolves it.
2. Implement candidate-free product entry/composition under [ISSUE-0008](../development/issues/ISSUE-0008-fix-free-product-investigation.md). Check positive and scoped negative baselines, failed control, missing witness, unchanged paired behavior and honest direct/durable support. No invented candidate or fix evidence.
3. Complete one positive pair and its independent negative through Python's full Docker product path, then another development topic for transfer. No demand for perfect scores before measuring breadth. Every stopped run is retained; unclear delivery/cleanup prevents dependent dispatch until reconciled.
4. Freeze source, agent versions, sanitized provider settings, images, dependencies, budgets, corpus/oracle identities and the 66-slot development inventory. Dispatch ready configurations in batches; preflight-blocked configurations remain visible with exact owner/reason. Complete each language's first sweep as its full execution/evidence path becomes available. A changing implementation receives a new candidate identity; do not combine different versions into one baseline or claim a partial language sweep is complete.
5. Publish a versioned baseline report, even if poor or mostly blocked. Keep each cohort/supported subset explicit. No baseline promotion requires a high score; it requires trustworthy identity, denominator and receipts.

**Cycle 2 — improve one measured cause.** Rank unsupported conclusive claims and false fix claims first, then repeated blockers affecting distinct topics, then agent errors, then efficiency. Freeze the relevant stage-input failure packet and a development comparison cohort before editing. Change one bounded behavior, compare the same isolated inputs against the reference (scripted contracts and live agent evaluation where applicable), then replay the same Docker cohort plus one untouched development transfer family. Retain both candidates and every failure. Improvement must preserve evidence validity and show no new unsupported decisive claim; if samples are too small or tradeoffs unresolved, record a candidate rather than declaring a winner. Set repeat counts and empirical regression thresholds before evaluating the candidate, once baseline variability is known.

**Cycle 3 — test transfer and expand coverage.** Freeze the candidate before held-out evaluation. Run supported held-out cases through an explicit evaluation-only path after implementing its split/label safeguards; do not bypass the development-only runner guard when that runner is integrated. Report held-out aggregate results separately and avoid case-level tuning leakage. Advance the next framework/effect slice and repeat the same pilot-to-sweep sequence. If held-out failures are inspected for tuning, retire the exposed family from future untouched claims, preserve the old manifest/results and admit a new separately versioned holdout. Never silently rewrite the original manifest.

These are milestones, not promises that all languages become runnable in three batches. Each finite execution iteration is capped at 24 full investigations; readiness/isolated work has separate declared limits. A milestone can require several iterations: this clarifies the earlier "24 per cycle" terminology without increasing the per-iteration allowance. The 66-request first sweep therefore spans at least three batches under that ceiling and more when pilots or repeats consume slots. Continue finite baseline batches before calling the sweep complete. Freeze a batch's slot list, model/tool budgets and live-resource owner before dispatch; stop when its allowance is spent. No new automatic retry or generic recovery engine.

## Parallel work allocation

Use up to three workers plus a coordinator when four agent slots are available; reduce parallelism to the actual environment. Prefer Sol workers where available, or use the session’s supported agents. Assign isolated branches/checkouts and disjoint ownership; coordinator owns shared integration, records, scorecard and the live-resource queue.

| Worker | Initial component | Completion evidence |
| --- | --- | --- |
| Shared path | Environment/planning/authoring approved-path contract | Reproduced failure, frozen isolated comparison, affected consumers, one diagnosed product successor |
| Baseline negatives | ISSUE-0008 optional-candidate product slice | Positive/negative and missing-evidence checks, no fabricated fix, paired regression comparison |
| Language admission | One complete JavaScript or Perl slice, then Java and C prerequisites | Real setup/discovery/two-test execution/effect/assessment path; image controls alone are insufficient |

Readiness from any prior local campaign is reusable only after verifying source/image identities and obtaining its receipts; do not assume those changes or artifacts exist in a fresh checkout. JavaScript next needs dependency capture for lockless projects, real-case matrix admission and an effect recorder; Perl needs product setup plus process/file evidence; Java needs current-source image provenance, Maven setup/framework compatibility and JVM evidence; C needs compiler, exact discovery/test protocol and sanitizer attribution. Prefer reusable boundaries with demonstrated consumers; do not hard-code topic names, expected verdicts or fixture-specific exceptions. Language ownership may rotate as a bounded slice finishes.

Keep one Docker build/native pilot/model campaign owner initially because the local endpoint and host are shared. Parallel preparation and isolated checks can continue. Increase live concurrency only after separate evidence roots, immutable cleanup ownership, endpoint capacity and comparable measurements are established; record concurrency in candidate identity.

## When the current set stops finding weaknesses

A clean run triggers a coverage audit, not a universal-correctness claim. Check that every intended request was accounted for, oracles are independently reviewed, supported positives and negatives produce valid evidence, no new unsupported conclusions appeared, and predeclared repeats/untouched evaluation support the result. All existing cases passing can still mean that the sample is too easy, narrow or familiar.

1. Identify missing families across language/framework, CWE/effect, repository scale, dependency complexity, safe refusal behavior, reachability, ambiguous reports and operational failures. Prioritize a specific untested capability, not merely a larger case count.
2. Search the existing [benchmark inventory](../benchmark-datasets.md) and evaluator-only imported external metadata first; then consider pinned public repositories with reproducible issues/fixes, realistic benign reports and independent synthetic counterexamples. Public provenance, licensing, exact revisions and dependency reproducibility are required. The imported Vul4J metadata is not admitted source or a ready-to-run cohort; follow its acquisition and proof-test masking requirements. No new examples were acquired in this planning session.
3. Deduplicate at repository/issue/family level before splitting. Reserve new families for a separately versioned untouched evaluation set before developers inspect them. Development authors may construct metamorphic variants (equivalent APIs, different layouts/input shapes, guarded or unreachable paths), but each needs an independently checked oracle and stays with its original family. Generated examples alone do not prove generalization.
4. Admit a small expansion batch, initially two to four independent families addressing the selected gap. Replay the trusted oracle under Docker, confirm exact discovery/control/effect evidence and masking, then add frozen evaluator metadata and neutral agent inputs. Unsupported and disputed additions remain unscored inventory with reasons.
5. Keep the original baseline cohort immutable. Report old-cohort regression and new-cohort performance separately; compute a combined result only with an explicit new dataset version. Maintain a bounded development regression set covering demonstrated mechanisms rather than copying every case into prompts. If the expansion exposes a failure, return to Cycle 2.

## Per-iteration record and exit conditions

Each iteration uses one small record in the existing plan plus native JSON/Markdown artifacts: hypothesis and owning component; frozen source/dataset/oracle/provider/image identities; scope and predeclared slots/repeats/budgets; reference scorecard; proposed change; isolated results; Docker comparison and transfer results; all errors/unknowns; cleanup; decision (retain reference, accept candidate for next comparison, or unresolved); and next experiment. Use `make eval` / `make eval-baseline` for stage references. Integrate and verify the proposed corpus `prepare|run|report` entry before using it for development runs; it is not present on the publication base of this runbook. A product baseline is a frozen campaign/report reference; do not invent a new promotion service.

Pause dependent execution when delivery or cleanup is uncertain, evidence contradicts the oracle, or a prerequisite is missing; continue independent work. End each finite batch with an honest report and resumable planned slots. A fresh-session handoff names the next bounded action and private evidence locations without exposing credentials. Existing authorization covers this development and delegated work; it does not authorize remote publication, deployment or scheduled background runs. Docker evidence remains unqualified for OpenShell/durable boundaries.

