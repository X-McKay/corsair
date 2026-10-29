# Intake Qwen route evaluation

Status: route correction and scoped evaluation completed 2026-10-29; scanner classification limitations remain open. Main base `f9e2ccca`. The user asked to continue after clarification that the `openai/` provider-route restriction is not a restriction on Qwen itself.

## Original evaluation boundary

Keep product code, native output schema, role resources, frozen fixture bytes/oracles and both cohort memberships unchanged. Test the existing `hosted_vllm/Qwen3.6-35B-A3B-NVFP4` route at the user's endpoint, then evaluate the original eight-case intake cohort and the separate 32-case JSON candidate cohort. Retain actual native ADK tool/skill counts, output validation errors, scored and operational failures, and unknown cost. No substitute provider, schema repair, baseline promotion or claim of full live workflow qualification.

Private configuration and raw diagnostics belong under `.state/intake-qwen-20261029` and `.runs/intake-qwen-20261029`. The new configuration identity is `d723fc80869517e2c5a9f3628fbae75b018f94420da6e0fafdc8af0a9f465196`. Production resource digest remains the merged main digest; model/route configuration changes independently. Frozen evaluation inventories are fixtures, not daemon-discovered image admission evidence.

## Plan

- [x] Run the eight-case cohort with the supported route; examine actual structured output and model/tool accounting.
- [x] Run the separate 32-case JSON candidate cohort without modifying its inputs or labels; retain every failure.
- [x] Record scoped results, correct current route guidance, and run quality/offline/package checks for any public changes.

## Commands and results

The original cohort is running with `nix develop --command uv run --locked --extra providers python -m corsair.evaluation.intake_agent evals/datasets/intake-capabilities.json --settings .state/intake-qwen-20261029/settings.json --repeats 1 --seconds 60 --output .runs/intake-qwen-20261029/original-8.json`. Full process output is retained privately. Result pending.

## Bounded correction design

A direct one-call LiteLLM probe reproduced `issue` as a string when its schema is only a `$ref`. Adding the equivalent `type: object` sibling to that same canonical schema made the endpoint return a dictionary that passed `IntakeProposal` validation. This matches upstream vLLM issue 46924; the exact server version/implementation is not attested.

Implement one canonical-field metadata change in `contracts/intake_agent.py`: retain `Issue` as the required Pydantic field and add `json_schema_extra={"type": "object"}`. This adds an explicit type without copying or dereferencing models, installing middleware, changing ADK's native completion tool, accepting strings, or repairing output. Schemas/resources receive a new digest. Add a native fallback-path test proving ADK forwards the explicit type and preserves the canonical schema; keep a regression that JSON-encoded issue strings remain invalid. Run affected tests, both frozen cohorts, native Docker/Temporal handoff, quality, package and outside-checkout resource checks. Retain earlier failures and the interrupted old-schema candidate report as separate diagnostics, never a model accuracy comparison across changed manifests.

The original eight-case baseline completed with eight `OUTPUT_INVALID` / `LLM_BUDGET_EXHAUSTED` results; all showed `model_type:issue`. The old-schema 32-case run was interrupted after reproducing this failure to avoid mixing schema resource identities. Its report retains all pending attempts as `not_run`. The explicit-type direct probe returned one valid native completion; this is transport conformance only, not agent accuracy.


## Executed correction

The canonical-field metadata attempt failed its native regression: Pydantic removes redundant type metadata beside a reference, and ADK rebuilds completion parameters from annotations, preserving descriptions rather than arbitrary field extras. It did not change the emitted schema/resource digest. The ineffective trial was interrupted after 4/8 invalid outputs, preserving the report and the remaining `not_run` rows. The contract edit was reverted completely.

The final fix lives only in `adapters/inference/intake_agent.py`. `IntakeAccounting.before_model` first calls the main accounting callback and preserves any denial. For the configured `hosted_vllm/` route only, it adds `type: object` to the native `set_model_response` issue parameter if its existing `$ref` resolves to the generated `Issue` definition with that object type. No canonical schema copy, custom tool, response repair, new loop or permission was added. A native regression proves the generated declaration, unchanged non-hosted route, unchanged canonical schema, strict string rejection and native call-budget exhaustion. Forty-two focused unit/security/evaluator checks passed. A fresh read-only reviewer found no blockers and suggested the route-isolation/budget tests, which were added.

The final private settings use `settings-native-object.json`; configuration identity `f95887944896f202e99b82e6b9a788c7c8941724f0d22583099fe4285bd2d374`, role-resource identity `0dabcb352d5b46493752ff829d96accec632a997af36feed2dde4d50c54b682b`. Canonical contracts and frozen manifests/fixtures are byte-unchanged from main. Provider: user's endpoint, model `hosted_vllm/Qwen3.6-35B-A3B-NVFP4`, ADK 2.13.0, LiteLLM 1.106.3. Exact server/parser version is unknown; the diagnosis is consistent with upstream vLLM issue 46924, not a server-side attestation.

## Final frozen diagnostics

Both final commands use `nix develop --command uv run --locked --extra providers python -m corsair.evaluation.intake_agent DATASET --settings .state/intake-qwen-20261029/settings-native-object.json --repeats 1 --seconds 60 --output REPORT`. DATASET is respectively `evals/datasets/intake-capabilities.json` and `evals/datasets/intake-json.json`; private REPORT paths are `native-object/original-8.json` and `native-object/json-32.json` under the retained run directory. Source inspection uses real Docker; the inventory is the frozen fixture inventory, not production image-admission evidence. Oracles stay evaluator-only.

| Cohort | Planned/completed | Exact pass | Classification correct | Invalid | Operational failures | False supported |
| --- | --- | --- | --- | --- | --- | --- |
| Original capabilities | 8/8 | 7/8 | 8/8 | 0 | 0 | 0 |
| JSON scanner candidates | 32/32 | 25/32 | 30/32 | 1 | 0 | 1 |

Original: 11 model calls, 12 accounted tool calls, including 3 `compare_images`, 8 native completions and 1 successful skill refresh. Reported tokens: 50,772 input / 7,421 output; sum of episode seconds 84.16. The service case omitted two of three expected requirements despite the correct unsupported classification.

JSON candidates: 58 model calls, 63 accounted tool calls, including 25 `compare_images`, 32 native completions, 1 `read_file` and 5 successful skill refreshes. Reported tokens: 285,384 input / 36,248 output; sum of episode seconds 374.97. Exact mismatches: Unicode fact preservation; invalid output for multiple distinct issues; a **false-supported contradictory report**; missing expected reasons for empty input/results; inferred details for a title-only report; and dependency execution mode. No nested `issue` completion errors remain. The false-supported case is a live classification defect, not a safe-to-execute or whole-workflow qualification result. No prompt, oracle or fixture was changed to make the score pass.

Each cohort has one repeat, so repeat stability is unmeasured. Cost stays unknown. These authored candidate cohorts are not held out, human-promoted baselines. The sum of episode times is a narrow run measurement, not an overall performance comparison. Raw outputs and failed/interrupted diagnostics remain private. The baseline candidate report has 7 completed invalid rows / 25 unrun rows; it is incomplete and is not a 32-case pass/fail measurement. The original baseline has all 8 invalid rows.

## Delivery gates

Final delivery commands and observed results:

- `TERM=xterm-256color nix develop --command just check`: pinned Ruff lint/format, Just format, ty with warnings failing, and local docs passed.
- `TERM=xterm-256color nix develop --command just -- test -q -W error`: **1,165 passed / 133 deselected**, 26.19s. Includes wheel installation and resource/schema/API loading outside the checkout. An earlier run before the route-isolation and budget tests passed 1,163 / 133; the final expanded count is used here.
- `CORSAIR_LIVE_CONFIG="$PWD/.state/intake-qwen-20261029/settings-native-object.json" TMPDIR="$PWD/.work/tmp" CORSAIR_TEST_DOCKER=1 CORSAIR_TEST_TEMPORAL=1 nix develop --command uv run --locked --extra providers pytest -q -W error tests/integration/test_intake_pipeline_chain.py tests/integration/test_chain.py tests/integration/test_intake_chain.py tests/integration/test_intake_inspection.py tests/workflow/test_agent_intake_workflow.py tests/workflow/test_intake_pipeline_workflow.py tests/replay/test_history.py`: **33 passed**, 145.08s, no deselections. Includes a real live Qwen intake child on Docker/Temporal. The investigation producer/auditor handoff tests in this set still use scripted native models; this does not establish a full live intake-to-investigation chain. Earlier no-live native run: 32 passed / 1 deselected, 133.41s, before the callback correction.
- `nix develop --command just build`: wheel and sdist built, 194 entries each. Inspection verified wheel package bytes match current source and private/cache paths are excluded from both archives. An initial inspection used system Python without the package and failed import; corrected inspection used the one root `.venv`. The preexisting UV build-backend version-range warning remains explicit.
- Both complete final frozen reports were checked against the current role-resource digest after all product edits. Frozen manifests/fixture bytes and canonical contracts are unchanged. No dataset rewrite, baseline promotion, output repair, credentials or raw diagnostics were committed.
- Fresh read-only review found no blockers; suggested route-isolation and budget-exhaustion regressions were added and passed.

See [ISSUE-0001](../../active/ISSUE-0001-intake-conflicting-reports.md) for the remaining false-supported candidate case. Other mismatches above remain limitations. Source changes and sanitized records can be committed as the authorized main follow-up; the original merge history is retained, with no force update.
