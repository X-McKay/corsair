# Issue-analysis fixture contract checks

The [read-only template](../development/specs/SPEC-0014-issue-analysis-template.md) implements one explicit saved-fixture PydanticAI agent. Its scope is structural contract behavior on PydanticAI/Pydantic Evals 2.55.0 with synthetic in-memory source, not live reasoning, provider compatibility, Temporal durability, OpenShell or application security verification.

The [implementation plan](../development/plans/PLAN-0016-issue-analysis-template.md) retains exact commands, failed attempts and coverage. The current isolated suite passes 26 checks in 0.35s (one native run_sync deprecation warning). Final native evaluation 003 runs three development cases twice, concurrency 1: 6/6 completed, 30/30 assertions, zero task/evaluator failures, exact repeat output agreement and six observed case trace identities. A separate negative test proves absent model spans fail the explicit coverage predicate.

The observed eval trajectory is ten scripted model responses and four source reads. FunctionModel estimates984 input/528 output tokens; those are not provider billing measurements. Summed native case task duration is0.056071858s; this tiny deterministic suite establishes no production latency percentile/SLO. Successful scripts require no output correction. Request/tool/token limit refusals and model exceptions are tested separately.

Source/read/output guards reject unlisted/traversal/absolute/noncanonical keys, invalid/oversized reads, fabricated/unread/prior-run-only quotations, scope expansion, extra finding/fix conclusions and ready results with missing facts. Independent review found and confirmed correction of the prior-history provenance gap; the final code requires a current native run ID on source-read message evidence. Native override restores the original model. Fixture/source instruction text is adversarial data, but scripted answers cannot establish live prompt-injection resistance or semantic correctness. Labels stay evaluator-owned in `evals/issue_analysis/oracles.json` and outside stage inputs/prompt/source. The CLI refuses existing report destinations and writes exclusively to preserve attempts.

Private native reports, logs, metadata and the current eleven-input `source-v2.json`/byte snapshot (including shared SDK lock/pins) remain under ignored `.runs/parallel-foundations-20261011/pydantic-agent/`. Earlier attempts/hash manifest remain historical. No credentials/model-provider calls or sandbox resources are involved; cleanup is not required. Production/live/durable gates remain unqualified. The two native finding-specific tests—benign control and security safety regression—are unchanged and are not replaced by these contract tests.


## Later prompt and provider assessments

The earlier26-check/evaluation003 metrics above describe the historical promptv1 snapshot and remain unchanged. Promptv3 adds exact one-based inclusive inventory/tool metadata and the supported native durability seam; current direct scripted fixture evaluation `.runs/four-priorities-20261012/pydantic-agent/fixture-evaluation-001.json` passes6 cases/30 assertions. Scripted estimates/local spans still do not qualify model reasoning. [PLAN-0018](../development/plans/PLAN-0018-local-issue-analysis-provider.md) records separate real-provider attempts and semantic failures; [native Temporal fixture qualification](issue-analysis-temporal-fixture.md) records durable fixture evidence.

## Native citation references (2026-10-12)

SPEC-0019 supplies the procedural skill via native Capability and the sole reader via FunctionToolset. SPEC-0020 then gives the model a Pydantic reference-only draft and uses a native async output function to check scope/current-run read coverage and supply exact source quotes. The public final IssueAnalysis JSON schema remains identical to the pre-change schema. Final oracle equality is unchanged; deterministic model helpers project quotation-bearing expected results into draft references outside agent-visible inputs. Native deterministic evaluation remains6 cases/30 assertions; full offline270/5.82s passed with the existing event-loop deprecation warning. Actual provider semantics remain separately gated by ISSUE-0007.


The subsequent evidence-coordinate skill/tool candidate passes full offline271/5.82s and deterministic6 cases/30 assertions. A native correction test exercises invalid local citation coordinates followed by a valid result with exactly one source read, preserving current-run validation. An initial full-suite failure on the deliberately changed inventory label is retained; its exact-label assertion was updated, without changing evidence gates.

The current numbered SourceRead/SourceLine tool representation passes272 offline checks/5.82s and deterministic6/30. Native provider wire and blank-line/range-order tests verify explicit local numbering without duplicated quote text; final IssueAnalysis schema and exact quotations remain unchanged.
