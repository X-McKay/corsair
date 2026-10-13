---
id: PLAN-0051
kind: plan
title: Planning agent review and source grounding
status: complete
updated: 2026-10-13
related: [SPEC-0047, SPEC-0022, PLAN-0038, ISSUE-0007, ISSUE-0006, HANDOFF-0071]
---

# Planning agent review and source grounding

## Objective and dependencies

Comprehensive bounded review of the planning agent at base 6be1b5f55224cbf97dc03a89f8c8a29d79f19df4, followed by independently reviewable source grounding improvements under SPEC-0047. The full application remains unqualified under ISSUE-0007 and ISSUE-0006. No cluster, container or model-authored code execution is needed.

## Steps

- [x] Read repository workflow, architecture, investigation/evaluation contracts, planner spec/plan/handoff and actual source.
- [x] Freeze a scripted development baseline through make eval AGENT=planning.
- [x] Tighten trusted target grounding and add native positive/negative tests.
- [x] Compare scripted candidate and run affected/offline checks.
- [x] Apply the review skill, record unresolved dimensions and prepare HANDOFF-0071.

## Comprehensive review

**Purpose and prompt/skill.** The factory has one narrow read-only task, an explicit unsupported branch and operator-provided environment facts. Prompt v6 and the mandatory skill preserve exactly two tests, untrusted source authority, scratch confinement, real implementation calls and no verdict. Historical PLAN-0038 provider results already show witness and semantic defects; this review does not relabel them as success. There is no justified new case-specific prompt recipe. Model correction feedback now explains the target citation gate; the prompt identity accounts for that text.

**Tools and trajectory.** Only the bounded saved-source reader is exposed; zero tool retries and current-run receipts constrain authority. Withdrawal after every inventory line was returned avoids useless re-reading once full coverage is reached. It does not prove optimal reads for a larger inventory. Repository-mode source tools remain a separate migration; introducing them here would broaden the boundary and budgets without qualification. No shell, network or execution path exists in this factory or planning eval.

**Contracts and findings fixed.** Current-run citation provenance alone allowed a ready plan to cite only unrelated saved tests. The implementation-call check also accepted a different symbol containing the target name. Each test now covers the supplied target source anchor and names its exact symbol. Adjacent ranges compose without a synthetic single-range restriction. These checks establish source association and lexical identity, not actual effect, full call graph coverage or test semantic adequacy.

**Pending work and consumers.** Ready plans without baseline evidence are an existing gap already addressed in pending PR44; its typed witnesses also address observation authority. Do not duplicate that work. Coordinate integration and identity changes after PR44 merges. The output schema remains unchanged for authoring and chain consumers. Existing affected consumer checks run in the full offline suite.

**Evaluation correctness and robustness.** The scripted model replays evaluator-only reference plans; 12/12 demonstrates plumbing and preserved contracts, not model quality. Native refusal tests cover forged grounding and symbol confusion independently of those oracle replays. Required-read checks, unknown-tool counts, native spans and task failure receipts remain useful trajectory/robustness coverage. Curated marker checks cannot resolve wrong fixture geometry, semantic contradiction, mocked sinks or unavailable event witnesses; actual output review remains necessary. No frozen dataset or manifest is edited and no held-out answer is used for tuning. Existing held-out plumbing tests do run as part of the unchanged test suite.

**Measurement and limitations.** Summary/comparison files retain mode, dataset, versions, requests, tools, latency and estimated tokens. Missing live usage is unknown. No local live config was independently configured; root serializes the shared provider budget. Live baseline/candidate comparison is pending root-owned follow-up. No durable replay, real corpus, sandbox replay or infrastructure qualification was performed here.

## Validation and progress

Evidence and actual final command results are recorded in HANDOFF-0071. An initial new-test run had 38 passes and two failures because the supposed non-anchor interval was actually the supplied anchor; corrected those two test inputs to lines outside it. That was a test construction error, not a bypass of the gate. The initial candidate scripted run passed 12/12 before the prompt identity was corrected; the final candidate is measured again under its final identity.

## Decisions and next action

No shared eval runner or Makefile change, custom evaluator framework or extra tools. Preserve this independent PR's scope; root may run the bounded live comparison and record failures without tuning on exposed held-out answers. Source grounding is admitted offline only; semantic/provider qualification remains blocked. Review and handoff use the repository skills.

Root integration follow-up: merged current main42a7273 into this PR branch, preserving both CURRENT entries after a documentation-only conflict. Further live planning evaluation was rejected before dispatch by automatic approval review because it interpreted host-only authorization as excluding transfer of synthetic fixtures to the configured external model endpoint. No workaround or provider retry; offline results stand.

## Current-head review correction

Independent review confirmed that Python regex \w excludes valid Unicode identifier continuation marks: a suffixed combining accent was admitted as an exact target. Literal matches now inspect adjacent characters using Python's identifier-continuation check plus Java/JavaScript $. Negative native stage tests cover combining and spacing marks; exact Unicode spellings and existing punctuation/dollar cases remain supported. This lexical rule remains conservative and is not semantic source proof. Prompt/config identity advanced to grounding-2 (planning config v4). No dataset/held-out changes or live provider calls. Earlier broad review-test attempts were interrupted after they stalled in the restricted worktree; subsequent focused checks and scripted comparisons are recorded below.

Focused target/anchor checks:10 passed; development scripted12/12 versus12/12, `.runs/evals/planning/20261013T100740Z-development-scripted`, unchanged estimated requests/tools/tokens.

Final affected planning and documentation/dataset guards:52 passed, one existing event-loop deprecation warning. git diff --check passed. Live candidate rerun and full-suite repeat unrun; prior full-suite source remains separately recorded.

## Conservative cross-language lexical follow-up

Cross-review found Java/JavaScript currency symbols and format characters still accepted as partial-name suffixes. The adjacent-character guard now conservatively includes Unicode Sc and Cf categories together with Python identifier continuations; this covers currency and zero-width joiner/non-joiner suffixes while preserving complete literal spellings. It is intentionally not a parser or declaration/semantic proof. Native negative and complete-spelling checks retain existing dollar and punctuation expectations. Identities advance to grounding-3 (planning config v5). No corpus/held-out, provider or authority changes.

Focused native admission/evaluator checks:21 passed, one existing deprecation warning. Final scripted development12/12 against12/12 at `.runs/evals/planning/20261013T101200Z-development-scripted`, unchanged estimated requests/tools/tokens. The independent implementation_call scorer now applies the defined lexical boundary rather than a substring; mutated-output negatives prove prefix and Unicode suffix sensitivity.
Full-suite repeat, live provider and runtime checks unrun for this bounded correction; earlier checks remain historical. git diff --check passed.


Current-main integration review (2026-10-13): main 8606068 merged cleanly.
Planning/configuration checks: 63 passed; unchanged frozen host-only Make suite 12/12.
No new source behavior, corpus changes, provider calls or runtime qualification.
