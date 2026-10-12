---
id: PLAN-0018
kind: plan
title: Local issue-analysis provider qualification
status: blocked
updated: 2026-10-12
related: [SPEC-0016, PLAN-0016, ISSUE-0007]
---

# Local issue-analysis provider qualification

## Objective and dependencies

Qualify one explicit native local OpenAI-compatible model using the [SPEC-0014 factory](../specs/SPEC-0014-issue-analysis-template.md) and only synthetic saved source. [SPEC-0016](../specs/SPEC-0016-local-issue-analysis-provider.md) freezes scope. Root owns shared dependency install, current/handoff, Git and cross-component checks; Temporal owner independently exercises durable fixture composition.

## Steps

- [x] Inspect repository/current/handoff, verify unused IDs, research native provider docs and perform TLS-verified read-only discovery; communicate one selected model/protocol to root.
- [x] Coordinate exact openai extra pins/install with root; add minimal explicit SDK-backed provider composition.
- [x] Define finite semantic rubric/four synthetic cases and meaningful negative checks; run offline provider/evaluation tests before inference.
- [x] Exercise actual endpoint with small budgets, native local traces, repeat/evaluation reports and attributable retained failures/usage.
- [x] Review finite qualification scope, freeze exact inputs/results, complete records/runbook and hand continuity to root.

## Validation and progress

Evidence root: `.runs/four-priorities-20261012/pydantic-agent/`. Initial restricted-host discovery failed DNS errno−3, retained `discovery-_v1_models.json` and `discovery-_api_tags.json`; escalated authorized TLS-verified reads then succeeded. `discovery-native-_v1_models.json` records 200, one vLLM model `Qwen3.6-35B-A3B-NVFP4`; `discovery-native-_api_tags.json` records 404. Both intended credential environment names (`CORSAIR_LOCAL_MODEL_API_KEY`, `OPENAI_API_KEY`) are absent; no values/secrets were printed or searched.

Root installed the selected slim[openai,temporal]2.55.0 extra with OpenAI3.29.0/tiktoken0.14.0 and locked closure; primary metadata is retained in `openai-pypi.json`/`tiktoken-pypi.json`. Existing distributions are unchanged except slim's optional dependency metadata gained the requested extra. No installation was performed by this lane.

Offline001 stalled at the native SDK's executor/event-loop wake path in the restricted host (bounded45s timeout, no final result); diagnostic001 at5s showed idle executor worker/main asyncio selector. Authorized unsandboxed offline002 passed42 checks in0.63s. Offline003 passed43/0.65s after exact source line-count inventory metadata; offline004 passed45/0.63s including guarded-source contrast and unavailable-usage negatives; offline005 passed45/0.65s after documented native JSON-schema profile selection. Native run_sync event-loop deprecation warning is retained. Offline SDK tests use native MockTransport, make no real provider requests and cannot qualify real authentication failures.

Actual local inference attempts remain distinct:

| Attempt | Actual result |
| --- | --- |
| live001 | One response, reported1138 input/166 output tokens (114 reasoning); agent chose read_source1..80 for4-line source and strict toolretry0 refused. This is tool selection failure, not provider unavailability. |
| live002 | Exact-line promptv2 admitted read_source1..4. Three responses/one read, reported4966 input/1506 output tokens (597 reasoning); native structured tool output repeatedly supplied hypothesis as a JSON-encoded string. Output correction budget1 exhausted with original Pydantic ValidationError/cause retained. No custom repair or raised budget. |
| live003 | New explicit native JSON-schema response profile candidate; One response516 input/176 output (124 reasoning),1.707s; model selected zero-based0..3, strict0retry refused. This revealed missing index semantics in the tool description. |
| live004 | Promptv3 read1..4 succeeded, but native JSON/tool grammar combination returned prose and exhausted response2048 budget:3 responses/one read,2584 input/4057 output (3569 reasoning),34.845s. |
| live005 | Native strict-tool capability disabled restored final JSON constraints but prevented source selection:2 responses/zero reads,1236 input/406 output (282 reasoning),3.815s. Domain validator correctly refused ready/null hypothesis. |
| live006 | Native prompted output with multiple leading system messages received original HTTP400 System message must be at beginning. No successful native response or provider usage; zero native counters are not provider zero usage. |
| live007 | Native prompted/single-system profile produced a typed hypothesis with one actual source read/exact quote after one output correction:3 responses,4284 input/2578 output (1814 reasoning),19.7s. Five of six assertions passed; finite semantics rejected missing target existence/read-permission preconditions. |
| live008 | Frozen4x2 characterization:3 typed completed/5 native failures; only2 missing-source attempts pass all assertions. Completed path lacks essential preconditions.18 responses/6 reads,24620 input/17239 output (14448 reasoning),145.987095398s summed receipt elapsed; provider usage all8,4 corrections/18 unique IDs. CLI exits1. |

After live001, root approved operator-owned exact line-count inventory in fixture_prompt; PROMPT_VERSION became issue-analysis-fixture-v2, with unchanged source authority/ranges/toolretry0. Temporal owner was notified before freezing shared factory. Existing promptv1 fixture reports are historical. The optional native TemporalDurability seam is coordinated and leaves domain contracts unchanged.

Independent review of root's SPEC0017 report consumer found no blocking issue within its explicit exact-stdout/untrusted-claims envelope; affected26 host tests independently passed0.31s (`report-review-tests.log`). Test discovery/semantic validity remain outside that consumer's claim.

## Decisions and next action

After live003, root approved one-based inclusive inventory/tool Field metadata in promptv3. Shared factory sha256e8b665253e2c47418dba34cb9e23b4476803f3a95b3703b9ed9f31dc17321f7b is stable and separately passed Temporal003; this provider profile does not alter it. Offline00649/0.66s and offline007–00949/0.64s passed. Current direct scripted fixture-evaluation001 passed6 cases/30 assertions with promptv3; it remains contract plumbing, not real reasoning.

Eight minimal512-token native schema probes retained exact requests/results. Tiny schema alone/tool-auto/strict-null passed; native strict read_source metadata suppressed final schema constraints. Removing only that strict field restored constraint enforcement. Selected vLLM0.30.0 [native parser source](https://github.com/vllm-project/vllm/blob/v0.30.0/vllm/parser/abstract_parser.py) independently shows tool grammar replacing response_format. Fullcase005 then proved that final response grammar prevents source tools, so this was not a full composition fix. Neither native JSON candidate is qualified.

The current explicit candidate uses documented native OpenAIModelProfile default_structured_output_mode=prompted, InlineDefsJsonSchemaTransformer, supports_json_schema_output=False, supports_json_object_output=False, openai_supports_strict_tool_definition=False and openai_chat_supports_multiple_system_messages=False. The SDK inserts its schema instructions and merges leading system messages; no manual message/JSON repair, protocol fallback, per-step scheduler or domain relaxation exists. The original HTTP400 validates the need for the documented single-system capability. Parent explicitly authorized one frozen4x2 matrix to measure current quality/consistency including failures, rather than tune this tiny fixture until pass. Runtime source-v1 freezes15 inputs before matrix dispatch.

Use only explicit `/v1` Chat Completions with the unique discovered model. The documented OpenAIModelProfile selects prompted output through native SDK schema instructions; read_source is the sole tool. This is explicit supported SDK configuration, not a provider/protocol fallback or weakened domain validation. Native captured tool arguments contained hypothesis as a JSON string; a qwen3_xml parser issue is a plausible inference, not an established upstream defect. Do not change the model deployment or add JSON repair. Do not infer immutable model weight identity from a served alias. Keep failed attempts. Typed/source-grounded007 success admits a frozen characterization matrix; its failed semantic gate remains a failure.


Final live008 freezes15 source/config/fixture/lock inputs in source-v1.json/byte copies before dispatch. Earlier live001–007 candidate attempts were not accompanied by full source copies; their native messages/prompt metadata/config/reports preserve diagnostics, but do not constitute fully frozen qualification baselines. Root independently recorded endpoint routing/serving image/cache provenance. The observed cache revision491c2f1ea524c639598bf8fa787a93fed5a6fbce matches public NVIDIA snapshot metadata/shard blob identities; loaded GPU weights were not hashed, and no deployment was changed. Native client closure is the only provider-lane cleanup.


## Final disposition and handoff

[ISSUE-0007](../issues/ISSUE-0007-local-issue-analysis-semantics.md) blocks semantic qualification. The native provider/read/typed boundary is observed, but frozen matrix fails quality/consistency: output correction exhausted once and response2048 token limit exhausted four times. The one completed path hypothesis omits target existence/read permissions. Its operation paraphrase and separate exact line3/line4 citations are legitimate, so two rubric flags are documented false negatives, not additional model defects. Do not tune/rerun in this slice. Three completed cases have17/18 assertions passed; this does not represent all8 attempts. Both missing-source outcomes agree on declining a hypothesis, despite prose differences. Guard and hostile-source runs have no final semantic verdict. Native report retains trace identities/coverage assertions, not full span exports; failed-case span coverage is not asserted.

The [qualification report](../../qualification/issue-analysis-local-provider.md) and [runbook](../../runbooks/issue-analysis-local-provider.md) are complete. Source-v2 freezes final records plus the unchanged15 runtime inputs; source-v1 remains the actual pre-live008 baseline. Root and Temporal reviewer independently audited all15 hashes/real outputs/usage/read provenance and identified the same semantic defect and rubric limits. Root reports244 affected offline checks passed5.72s after final profile. Parent owns CURRENT/latest handoff/publication; no install, Git commit/push or service mutation was performed by this lane. Next bounded action is saved-output evaluator admission review before any separately planned prompt/model comparison.


Closing owned-record guards: tests/configuration/test_development_workflow.py passed4 in0.03s (records-001.log); git diff --check passed. Current runtime/provider/evaluator files stayed unchanged throughout live008; no further live inference was dispatched after its failures.

## Bounded continuation: evaluator admission and prompt comparison

The user requested continued testing/improvement with simplicity and explicit verification of both the benign control and security probe. Starting HEAD c83f0bf and PR18 exact-head CI38232983347 passed; workspace was clean. Root re-read live008's actual report (three completed/five failed) and verified all15 frozen input hashes against the starting committed source (the delegated evaluator edit had already started during the working-tree check); private audit is `.runs/local-model-improvement-20261012/baseline-audit.json`. Original live008 remains immutable.

This continuation corrects finite operation-paraphrase/combined-citation evaluator false negatives with opposite-claim checks, then measures one promptv4 candidate against the same four cases/two repeats. Promptv4 only clarifies conditional environmental assumptions versus missing facts and asks for concise schema output; no fixture oracle facts, new tools, model/profile changes, serving changes, retries or budget increases. Freeze the corrected evaluator and candidate inputs before live work; compare against the preserved v3 result without counting offline rescoring as new inference. Root owns prompt/evidence/records; Sol independently owns evaluator correction and test-pair audit. Relevant offline checks precede inference; dependent real-provider integration remains blocked.

The test-pair audit must distinguish report-claim transport from application execution. The current native report producer prints literal claims; it is not a generated or executed application test pair. Actual drafting/discovery/target-path execution remains unimplemented/unqualified. Before that boundary can qualify, require exactly two tests, same immutable test patch on reviewed vulnerable/fixed fixtures, benign control passes on both, safe-behavior security assertion fails on vulnerable and passes on fixed, native discovery and individual fresh outcomes, real path/effect witnesses, and no sandbox denial/skips/build/setup errors misclassified as application safety. No custom runner or semantic attestation is added to the report consumer.
