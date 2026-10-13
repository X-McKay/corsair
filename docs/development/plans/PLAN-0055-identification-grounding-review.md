---
id: PLAN-0055
kind: plan
title: Identification grounding review
status: complete
updated: 2026-10-13
related: [SPEC-0051, SPEC-0024, SPEC-0038, SPEC-0044, HANDOFF-0070]
---

# Identification grounding review

## Objective and dependencies

Review both identification modes across prompts, procedural skills, tools/contracts and evaluation, then fix concrete grounding defects independently of runtime infrastructure. Base `6be1b5f55224cbf97dc03a89f8c8a29d79f19df4`; branch `codex/agent-identification-improvements`. No kind/OpenShell/container or untrusted execution is needed.

## Steps

- [x] Read instructions, architecture/evaluation boundaries, SPEC-0024/PLAN-0024/HANDOFF-0040 and SPEC-0038/HANDOFF-0060; inspect source and establish baseline.
- [x] Review the four surfaces and implement bounded occurrence/quotation improvements with regressions.
- [x] Complete candidate comparisons, final guards and review.
- [x] Record results, update current index/handoff, commit for root-owned publication.

## Validation and progress

Baseline scripted: `PATH=/tmp/corsair-identification-bin:$PATH make eval AGENT=identification NOTE=pre-change-scripted-baseline`, run `20261013T094459Z-development-scripted`, 16/16 clean, no failures; temporary uv shim delegates the exact Python/module arguments to `/home/al/git/corsair/.venv/bin/python`. Subsequent Make verification uses the actual uv at `/home/al/.local/bin/uv` with `PYTHONPATH=src:. UV_PROJECT_ENVIRONMENT=/home/al/git/corsair/.venv UV_NO_SYNC=1`; dependencies/lock remain unchanged. Focused native checks: 65 passed, one existing event-loop deprecation warning.

Private baseline source copies and manifest, provider configuration and logs are retained in `.runs/identification-review/`. Live baseline `20261013T094541Z-development-live` uses the explicit documented `vllm` endpoint/model, default response cap 2048 and timeout 60 seconds, with unchanged suite budgets (two repeats, four requests, three tools, total 32000 tokens, task 180 seconds, one output correction). Candidate comparison completed below. Provider calls carry only saved synthetic fixtures.

## Decisions and next action

Review findings and dispositions:

| Surface | Finding and action |
| --- | --- |
| Prompt | Narrow localization, trusted issue preservation and untrusted-data separation remain appropriate. Keep prose unchanged; version model-visible new validation feedback. |
| Skills | Inline skill checks bodies rather than names and distinguishes guards from verdicts; repository skill searches first and follows delegations. No evidence justifies extra instructions. |
| Tools/contracts | Existing confined reads, current-run read coverage, repository identity/budget, zero tool retries and explicit modes remain intact. Fix substring/whitespace symbol acceptance in their shared finalizer. |
| Evaluations | Frozen oracles reject wrong targets/ranges but did not independently verify exact quote bytes. Add the quote assertion without changing cases/oracles. Scripted model is oracle-aware plumbing, never semantic-model evidence. |

Recommendations retained: independently reviewed held-out inline and multi-repository cases; meaningful abstention-reason evaluation without turning wording into a lexical oracle; explicit repository eval entrypoint/fixture corpus before broader qualification; repository durable serialization and downstream migration remain separate gates. The occurrence guard deliberately cannot establish declaration/body relevance or reject every comment/string coincidence. Do not claim arbitrary source-semantic proof or live repository readiness.

Final actual Make verification: `PATH=/home/al/.local/bin:$PATH PYTHONPATH=src:. UV_PROJECT_ENVIRONMENT=/home/al/git/corsair/.venv UV_NO_SYNC=1 make eval AGENT=identification NOTE=final-grounding-version`, run `20261013T094930Z-development-scripted`, 16/16 clean, unchanged mean 1.75 model requests and native receipt totals 12 tool calls across 16 attempts. Earlier intermediate scripted run `20261013T094731Z-development-scripted` also passed 16/16; it preceded the final distinct grounding version identifiers.

Same actual Make environment with `PROVIDER_CONFIG=.runs/identification-review/provider.json` produced candidate `20261013T094931Z-development-live`, 16/16 clean, zero task/evaluator failures, unknown tools and output corrections. All target/range/quote checks pass 12/12 ready outputs; four abstentions pass. Provider usage and model spans cover 16/16 both baseline and candidate. Native receipt totals: baseline 30 requests / 14 successful tools / 42949 input / 12348 output tokens / 174.571 seconds summed task wall time; candidate 30 / 14 / 42771 / 10360 / 144.894 seconds. Observed summed reasoning tokens: 10722 to 8777. These are two exposed-case runs without repeat-statistical inference; lower observed tokens/time do not establish an efficiency or general quality gain. Both retain correct selections. The negative regressions establish a stricter contract.

Added exact-quote assertion was also applied separately to retained baseline outputs: 16/16 pass; original baseline report unchanged. First helper command omitted PYTHONPATH and failed with ModuleNotFoundError before any provider dispatch; corrected host helper passed. Pydantic Evals drops zero-valued metric increments; summaries may average successful-tool metrics only over nonzero entries. Use native receipts/observed attributes for all-attempt totals (14/16 tools = 0.875 per attempt in each live run), not the summary's conditional mean 1.0. Missing telemetry remains unknown, not zero.

Required full actual `make test-config`: 1009 passed, one existing event-loop deprecation warning, 50.55 seconds. Focused 65 passed; record/link guards 5 passed after writing records. Candidate source/config/corpus/skill manifest verifies all eight entries unchanged after live execution. Final diff review applied the Corsair review skill; root reviewed code/records and found no blocker. No dependency installation, infrastructure, repository live smoke, new Temporal execution or untrusted host execution occurred. Historical repository mode still requires broader independent evaluation, durable serialization and downstream admission; this work does not renew those claims.

## Current-head review correction

Independent review confirmed that Python regex \w excludes valid Unicode identifier continuation marks: a suffixed combining accent was admitted as an exact target. Literal matches now inspect adjacent characters using Python's identifier-continuation check plus Java/JavaScript $. Negative native stage tests cover combining and spacing marks; exact Unicode spellings and existing punctuation/dollar cases remain supported. This lexical rule remains conservative and is not semantic source proof. Prompt/config identity advanced to grounding-2. No dataset/held-out changes or live provider calls. Earlier broad review-test attempts were interrupted after they stalled in the restricted worktree; subsequent focused checks and scripted comparisons are recorded below.

Focused Unicode/identifier checks:22 passed; development scripted16/16 versus16/16, `.runs/evals/identification/20261013T100737Z-development-scripted`, unchanged estimated requests/tools/tokens. SPEC-0051 and PLAN-0055 replace this branch's previous colliding identifiers; all tracked references updated. These are new record identities, not changes to the other PR's records.

Final affected identification/repository and documentation/dataset guards:77 passed, one existing event-loop deprecation warning. git diff --check passed. Live candidate rerun and full-suite repeat unrun; prior full-suite source remains separately recorded.

## Conservative cross-language lexical follow-up

Cross-review found Java/JavaScript currency symbols and format characters still accepted as partial-name suffixes. The adjacent-character guard now conservatively includes Unicode Sc and Cf categories together with Python identifier continuations; this covers currency and zero-width joiner/non-joiner suffixes while preserving complete literal spellings. It is intentionally not a parser or declaration/semantic proof. Native negative and complete-spelling checks retain existing dollar and punctuation expectations. Identities advance to grounding-3. No corpus/held-out, provider or authority changes.

Focused native inline/repository identifier checks:28 passed, one existing deprecation warning. Final scripted development16/16 against16/16 at `.runs/evals/identification/20261013T101223Z-development-scripted`, unchanged estimated requests/tools/tokens.
Full-suite repeat, live provider and runtime checks unrun for this bounded correction; earlier checks remain historical. git diff --check passed.


Record-accuracy review (2026-10-13): CURRENT now separates the grounding-1 exposed-case
live comparison from grounding-3 scripted-only checks. The original 1009-check result remains
a historical grounding-1 result, not final-head qualification. Removed erroneous planning
configuration references. The 20261013T101223Z run evaluated uncommitted grounding-3
changes on 9b6065e, subsequently committed as e9922b7; it was not a live run.
Current main 8606068 merged cleanly; no source behavior changed in this follow-up.
Affected identification/repository/configuration checks: 83 passed. Frozen host-only
Make remains 16/16 after integration. No live/provider evaluation repeated.
