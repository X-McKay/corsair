# Independent probe agent baselines

This is an implementation and isolated-agent checkpoint for [SPEC-0079](../development/specs/SPEC-0079-independent-probe-authoring.md) and [PLAN-0094](../development/plans/PLAN-0094-independent-probe-authoring.md). The production path now has independent source-only control and exploit authors, followed by a separate outcome-blind validity call, native execution and result assessment. The initial ordered baselines expose fixture, evaluator and agent defects. They do **not** qualify the complete composition, production semantic review or additional runtimes/frameworks. Completed pre-manifest corrected measurements are recorded below; fresh measurements of the final native-manifest source are **UNRUN / deferred by user instruction**.

The user authorized finishing the ordered baselines and publishing the resulting PR toward main. This report does not authorize deployment or issue closure. Local raw reports, provider messages, source archives and review exports under `.runs/split-transition-baseline/` remain private and excluded from publication. Public counts below summarize those receipts without copying their raw contents or naming held-out cases.

## Measurement envelope

The repository pins PydanticAI/Pydantic Evals **2.55.0** and Temporal **1.34.0**. Live isolated runs use the native vLLM adapter and the configured **Qwen3.6-35B-A3B-NVFP4** model name. A weights digest and server/hardware identity are **unknown**. Recorded request settings are temperature 0, parallel tool calls disabled, maximum response 8,192 tokens and a 2,048-token thinking budget; the provider timeout is 180 seconds. Structured output uses the recorded prompted profile. SDK retries and task retries are zero. Each set runs serially with one repeat; this measures neither repeated-run consistency nor concurrent latency.

An isolated author uses ceilings of 20 requests, 20 tools, 128,000 tokens and 900 seconds, with two output retries. Current composition uses the same role factories and ceilings but derives narrower effective allowances from source windows, write/refusal allowances and output retries. For example, one source window derives six tools, ten requests and 120,000 tokens. Factory reuse alone does not make isolated and composed budget measurements equivalent. The composition retry/ceiling correction is recorded separately from the original frozen live source.

Environment fixtures inject deterministic setup observations; no setup command executes on the host. Identification/planning transfer inputs are saved source and operator fixtures. Planning fixture baselines are injected identities for reasoning, not newly observed native setup. Authors only read source and write their own proposed file; no generated test executes in these baselines. Source-only validity is a separate assessment call. Historical result-assessment cases use recorded/injected evidence and retain their original witness-mode scope. Current final-unit cases instead capture actual native outcomes of exact operator-reviewed fixtures, as described below.

## Initial ordered live results

These measurements remain bound to their original frozen inputs, oracles, skills, settings and receipts. Contract success is separate from semantic source review and native execution.

| Stage and preserved version | Contract/evaluator result | Independent source interpretation and limits |
| --- | --- | --- |
| Environment v9, development-v2 | **4/8 clean**; six typed outputs, two task failures | Ready proposals duplicated build work in both preparatory recipe and terminal build field. Deterministic observations were injected; no live setup qualification. |
| Identification transfer v1 | **2/8 clean**; target selection and quoted-source grounding **8/8** | The range oracle incorrectly required export/package/class boilerplate. Corrected-oracle reassessment of the same eight saved outputs is **8/8**, with no new model run. |
| Planning transfer v1 | **0/5 clean**; two typed unsupported outputs, three contract failures | Two positive fixtures had only a shared approved probe file and correctly became unsupported under the independent-file contract. Their correction does not relabel the three contract failures as successes. |
| Control author transfer v1 | **8/8 contract admission** | Independent source-only review **0/8 accepted**. Controls coupled benign behavior to security flags/representations; additional loading, selector, scope/capture and anchor defects occurred. Native execution **unknown**. |
| Exploit author transfer v1 | **8/8 contract admission** | Independent source-only review **1/8 accepted**. Native execution **unknown**; this is not production validity calibration. |
| Control author v2, frozen Python development set | **8/8 contract admission** | Actual control bodies **8/8 accepted** by separate source-only inspection; proposed assertion metadata **7/8**. A wrong anchor does not itself invalidate a sound body. Native execution **unknown**. |
| Exploit author v2, frozen Python development set | **8/8 contract admission** | Actual exploit bodies **6/8 accepted**; proposed assertion metadata **4/8**. Body validity, anchor fidelity and native execution are separate dimensions; execution **unknown** for all eight. |
| Validity transfer v1 | One correct rejection, two contract failures (**1/3 clean**) | Separate source-only `ValidityInput`; the valid-example failure and incomplete attempts prevent calibration. |
| Assessment unit-validity set | **4/7 clean**; three task failures | Report complete at this checkpoint. This is the source-only validity assessment set, not final result interpretation. Provider usage coverage is unrecorded/unknown. |
| Historical final result assessment, 54-case set | **STOPPED PARTIAL**: 14 retained attempt receipts, 11 typed completions and three failures at this read checkpoint; no final report | Preserve its original witness-mode dataset and outcome semantics. Undelivered/in-flight work is unknown; this is not a 54-case aggregate or the current final-unit baseline. |

The independent author source inspections used each attempt's own input and generated file only. They excluded provider reasoning/messages, native outcomes, the counterpart revision and result-report assertions. These inspections are independent source judgments, not native execution receipts or calibration of the production validity agent. Contract checks admit a bounded file, source reads, assertion anchors and typed completion; they cannot establish that imports resolve, selectors match, the code compiles or the assertions measure the reported condition.

## Recorded efficiency

The following totals come from attempt receipts, including unsuccessful attempts. Time is the sum of recorded attempt elapsed time, not an end-to-end product latency measurement. Usage coverage is recorded present for the first eight rows; unit-validity coverage is **unknown**, so its counters are observed totals with unknown completeness. Missing telemetry is not treated as zero.

| Preserved run | Requests | Tool calls | Input tokens | Output tokens | Attempt seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Environment v9 | 65 | 52 | 334,805 | 25,210 | 236.0 |
| Identification transfer v1 | 16 | 8 | 22,763 | 5,355 | 44.5 |
| Planning transfer v1 | 18 | 10 | 105,239 | 17,223 | 151.0 |
| Control transfer v1 | 27 | 16 | 67,057 | 26,509 | 210.2 |
| Exploit transfer v1 | 26 | 16 | 74,238 | 32,923 | 265.4 |
| Validity transfer v1 | 27 | 21 | 256,434 | 34,242 | 271.2 |
| Control Python v2 | 34 | 24 | 99,591 | 21,787 | 185.4 |
| Exploit Python v2 | 33 | 24 | 108,374 | 27,473 | 228.5 |
| Assessment unit-validity | 54 | 40 | 481,654 | 63,927 | 504.5 |

The sets and role objectives differ. These totals do not establish a quality or efficiency winner, a provider ranking, or a production capacity/SLO. The earlier joint/independent comparison remains a separate historical measurement in [the specialist comparison report](probe-specialists-comparison.md).

## Versioned corrections and fresh measurements

No original failing score is overwritten. Environment v10 distinguishes preparatory recipe commands from terminal build/discovery/baseline commands without changing enforcement or observations. Identification v2 records explicit operator-selected function lines instead of whole-file property citations. Planning v2 fixes distinct file/native-ID admission and local source targets. Author v2 adds generic identity/loading/namespace/scope/capture checks and keeps ordinary controls independent of security implementation details. These procedure changes introduce no language/CWE parser, new recorder, schema, tool authority or graph framework.

| Fresh corrected run | Result | Receipt/report identity |
| --- | --- | --- |
| Environment v10, development-v2 | **4/8 clean**, two task failures | Summary SHA-256 `97bc174591cac0df991eb52bf163889a75be6293db6d1d55544579fbe141a4fe` |
| Identification transfer v2 | **8/8 clean**, no task failures | Summary SHA-256 `2b4fefe9da7dc7714a9d88f81cf4d370e98cd86c7203d3316c41c763871ccaa8` |
| Planning transfer v2 | **1/5 clean**, all five typed contracts, no task failures | Summary SHA-256 `a3e7afb403562e48686290c02212f6f8fd2aecf4df3909e0dcade68cc604bb9d` |
| Control author v2, multilingual transfer | **UNRUN — user deferred** | No final-source model calls |
| Exploit author v2, multilingual transfer | **UNRUN — user deferred** | No final-source model calls |
| Final unit disposition v2 | **UNRUN — user deferred** | No final-source model calls |

These corrected measurements precede the final native-manifest migration; planning has four adversarial-input oracle failures despite contract completion. Some isolated suites overlapped historical assessment work, so latency is not a controlled comparison. Fresh author contract scores require another independent review of the actual generated source and assertion metadata. They do not inherit the earlier Python body scores. Native execution remains unknown until an admitted execution port actually runs both generated probes; node:test/RSpec conventions and the Perl assertion classifier do not automatically qualify native selection/outcome adapters.

## Current final-unit evidence

The bounded `assessment-unit-disposition-v2` corpus contains four actual final `AssessmentInput` objects captured through the existing production `run_chain`/`StageInvoker` ports. Callbacks delegate native production factories, prompts, dependencies and effective limits. Exactly the operator-reviewed two-file fixture patch runs on each mapped source revision: **eight revision runs, sixteen per-probe outcomes, all cleanup confirmed**. The final-only model inputs retain actual native evidence and immutable source/plan/patch-bound review. Operator expected gates remain outside model inputs. Source-absent cases are excluded because no final assessment call occurs.

Source-only fixture reviews are scripted operator plumbing; they do **not** calibrate the production validity model. Optional witnesses may support unit evidence but do not supply its validity. The final-unit evaluator checks native probe identity/outcome completeness, review binding, immutable evidence, gate/admission correctness, required reads and native receipt grounding. Its 600-second task ceiling matches current composition; the historical final assessment retains its 1,200-second default. Those settings must be reported separately.

The original final-unit v1 capture and manifest remain available for historical inspection. Its existing scripted reviewer incorrectly cited the first patch item for both probes. V2 cites each actual own-file import/call, literal input, property assertion and captured source definition. The Python AST use is confined to preparing/reviewing this known fixture, not production policy or a general language-specific recorder. Initial v1 scripted final scoring also failed receipt grounding because its fixture model preferred optional witness citations; that failed report remains preserved. The corrected scripted model cites actual native receipts and reads frozen reviews. **V2 scripted final evaluation passes 4/4**; the final-source live final-unit measurement is **UNRUN / deferred by user instruction**.

## Implementation checks and remaining gates

The latest pre-cleanup broad offline checkpoint was **2,326 passed, six skipped, ten warnings in 39.71 seconds**. The earlier 2,274-pass checkpoint and obsolete three-container expectation failure remain historical. Final instruction-ownership cleanup and receipt additions require a new whole-tree checkpoint before publication. Focused source/capture/evaluator checks passed, including both independent call/assertion quotations and rejection of custom metadata that attempts to override model, mode or budgets. All scripted suites passed: environment16/16, identification8/8, planning5/5, each author8/8, validity7/7, final disposition4/4 and chain5/5. One earlier invalid `unit-test` set selection was rejected by the CLI before model calls; the corrected `unit` command passed. Closing context: [HANDOFF-0130](../development/handoffs/HANDOFF-0130-native-manifest-baseline-checkpoint.md). Final offline checks and identity receipts are complete; fresh live measurements are deferred by the user.

[ISSUE-0009](../development/issues/ISSUE-0009-unit-review-semantic-validity.md) remains open. Source-only review failures, contract completion and scripted native fixtures cannot close the production semantic qualification gate. Full durable/provider/runtime composition and broader supported-language/framework claims remain unqualified.

[IDEA-0010](../development/ideas/IDEA-0010-native-agent-manifests.md) now authorizes native per-package manifest/operator-policy implementation in this PR under [SPEC-0080](../development/specs/SPEC-0080-native-agent-manifests.md) and [PLAN-0095](../development/plans/PLAN-0095-native-agent-manifests.md), superseding the earlier after-publication dependency. Preserve existing frozen baseline results and give migrated source new identities and measurements. The pinned SDK's `AgentSpec`, `Agent.from_spec()` and `Agent.from_file()` were verified against 2.55.0. All seven factory variants now use the trusted native helper with byte-parity evidence, including repository identification. Shared budget/model policy resolution is implemented. Instruction/shared-skill ownership cleanup, mutable-envelope guard and spec/selection/factory/helper identities are complete. Separately identified live measurements of the six roles and final assessment are unrun and deferred by the user. This is construction parity, not semantic or composition qualification.

## Original report digests

These SHA-256 values identify completed reports at this checkpoint; raw files remain private. Pending fresh runs will receive separate identities.

| Report | SHA-256 |
| --- | --- |
| Environment v9 | `c714358fd4992aafa7ea07ddffd4f6cae47f8616d7a2654a81b5a70c4a2aa313` |
| Identification transfer v1 | `422e73cf6eaf00368891aa479b8d70144fcb5558ddc3f957a0ef8e05ffebb927` |
| Planning transfer v1 | `0bdd0d2c112df42bf43b5c91b38856e27f261587e26729d6cfc1f17d3ccad3a6` |
| Control transfer v1 | `65e7f171866a79b5a722e876882c16c0389c62d9b25ab894146658e4cc1e699f` |
| Exploit transfer v1 | `cace971b298c11abb101739a1779b444485cc8786491252993db39f7df18354b` |
| Validity transfer v1 | `96271ae536ca8719ae1755d07ab2532aa25baf9c56f5e82b1a4ae6021d3b76c1` |
| Control Python v2 | `4de24dcc38f9dfc3d82f5f19da8dc7edba95be894129cbce16af2c047404af3e` |
| Exploit Python v2 | `1e3d7dfc02c3f56fae14822c8d5557bdf92d438d66867b19f1294d038b434498` |
| Assessment unit-validity | `f076dcdb3ef5e567288c1705cc97ecb5cc06d3f9234c22c1b460761b01688bb4` |

Final publication checkpoint (2026-10-13): implementation and identity/ownership cleanup complete. Root reports full offline **2,329 passed, six skipped, ten warnings in 51.95 seconds**, final targeted **60 passed**, and seven native factory parity **22 passed**. Final scripted suites pass: environment16/16, identification8/8, planning5/5, each author8/8, validity7/7, final disposition4/4 and chain5/5. Offline wheel inspection confirms ten YAML/shared-skill assets byte-equal to current source (`native-yaml-wheel-final-check.json` private receipt); the431-file source-freeze manifest remains ignored. These are offline/parity/fixture claims, not model quality or composition qualification.

The user explicitly deferred fresh post-manifest live baselines and requested the PR now. All seven planned live jobs are **UNRUN / deferred**. Automatic approval review rejected their earlier launch before any model calls. Corrected pre-manifest environment4/8, identification8/8 and planning1/5 remain historical measurements. ISSUE-0009 stays open. No endpoint calls occurred in this documentation lane; raw `.runs` exports remain private.
