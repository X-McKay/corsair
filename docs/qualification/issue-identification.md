# Narrow issue-identification baseline

The user accepted narrowing the first agent to locating the relevant implementation for a reported security concern, prioritizing accurate end-to-end results over latency. [SPEC-0024](../development/specs/SPEC-0024-issue-identification.md) and [PLAN-0024](../development/plans/PLAN-0024-issue-identification.md) implement and evaluate that isolated replacement. This is not a finding/fix verdict or full-graph qualification.

## Contract and deterministic checks

The model returns status, authorized scope, one source symbol/location or a concrete blocker. Trusted code preserves the complete original issue and constructs source quotations from successful current-run reads. There is no generated behavioral prediction, preconditions list or verdict. Report/source text remains untrusted task data when passed downstream; preservation does not grant it authority.

The component reuses native PydanticAI structured output, a mandatory procedural skill, Pydantic contracts and a restricted FunctionToolset. The final reader accepts a saved path and optional starting line, returns at most 80 numbered lines and determines the actual endpoint at EOF. It cannot access other paths, exceed the fixed window or borrow another run's read evidence. The original analyst's reader, hypothesis/reviewer factories and Temporal workflow remain unchanged.

Eight public development cases cover ordinary/guarded source, source/report instruction injection, missing source, renamed symbols, a same-name decoy, a Ruby command-operation example and an unrelated inventory. Ruby is read-only source data here, not runtime admission. Native Pydantic Evals compare explicit expected status, symbol/path and source ranges, with report identity, native budgets, usage, unknown-tool and span checks. There is no LLM judge or semantic word-matching evaluator. This small curated corpus cannot prove arbitrary source semantics, and abstention-reason prose is not semantically scored.

## Frozen attempts

All runs use the explicit native vLLM profile at the authorized `llm.almckay.io` endpoint, alias `Qwen3.6-35B-A3B-NVFP4`. Discovery confirmed the alias; loaded-weight identity and billing remain unknown. No deployment, TLS, policy or pin was changed. Each case runs twice at concurrency 1, request limit 4, tool limit 3, total tokens 32000, response cap 8192, client 120s and task 180s, default thinking without an imposed thinking cap, output correction 1, tool/SDK/task retries 0. No failed attempt was replayed.

| Candidate | Completion and checks | Diagnosis |
| --- | --- | --- |
| v1, live001 | Typed 16/16; raw all-check 7/16 | Six exact report-excerpt boundary flags; one wrong same-name decoy; two evaluation request-count flags caused by duplicate metrics. Actual receipt requests stayed within 4. |
| v2, live002 | Typed 15/16; all 15 completed outputs passed every check | One native tool failure: lines1–80 requested from a two-line file. No semantic verdict for that failed attempt. |
| v3, live003 | Typed 16/16; all 16 passed every check | No failed tasks, evaluator failures, unknown tools or output corrections. Both repeats selected the expected location or abstained as expected. |

V1's excerpt boundaries were unnecessary model work: trusted code now carries the full original issue. V2's general skill guidance checks the candidate's body rather than trusting a matching name. Manual counters moved to `observed_*`, leaving native request metrics unmodified; regression checks compare native metrics with receipt counts. V3 removes endpoint guessing from the read tool while preserving the hard 80-line bound and zero tool retries. Inputs and localization labels remain unchanged across all three candidates. Candidate-guided changes on this exposed development set are not held-out evidence; no original report was rewritten or rescored as a pass.

## Retained evidence and limits

Private `.runs/issue-identification-20261012/` holds original reports, per-attempt native messages/receipts, usage including failures, summaries and frozen source copies. V1 freezes 23 inputs (manifest SHA256 `ed891335a46481f1afc884ca0d9a84cd176c80ff2f08f3083c297a4689bbbaf5`); v2 freezes 24 (`bdc23315e58b926e20d320c135ed3b1eb6533fd12a27ac2730076f6c350897d9`); v3 freezes 25 (`ef7bf4ab4da199038c56e9f24cc9e335a8f59639abcd67a9fd201bfda49141e6`). Frozen copies and current runtime inputs were verified against each manifest immediately after its run. All 25 final inputs and copies match the v3 manifest. Native request/input/output metrics also match the per-attempt receipts.

V1 recorded 33 model requests/14 successful reads, 48560 input/20943 output/18455 reasoning tokens and 166.790s summed task latency. V2 recorded 29 requests/13 successful reads, 41287 input/11837 output/10049 reasoning tokens and 112.394s. Usage and reasoning coverage are 16/16 for both, including the failed tool attempt. V3 recorded 31 requests/15 successful reads, 44730 input/10163 output/8512 reasoning tokens and 92.065s summed task latency; usage and reasoning coverage are 16/16. There were zero output corrections or unknown-tool attempts. Counts are observations, not causal efficiency claims.

Final offline preflight passed 390 checks/6.88s, including 21 focused identification checks, with the existing event-loop deprecation warning. Initial failed offline checks are retained: a test assumed the SDK preserved trailing instruction whitespace, and the scripted model briefly omitted its citation endpoint during the tool-interface edit. Both were corrected before the corresponding live candidate ran. Native mock-transport checks verify actual schema/skill/tool delivery and client closure; scripted repeat evaluations do not prove model reasoning.

No Temporal/OpenShell process or historical project workload was created. Native HTTP clients close through the provider context manager. The old hypothesis/reviewer evaluations remain failed/unqualified under their original contracts. ISSUE-0007 stays blocked for end-to-end admission; broader independently reviewed cases, durable qualification, planner integration, real two-test execution and final disposition evidence remain separate work.
