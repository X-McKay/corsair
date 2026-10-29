# Qwen intake route diagnostic, 2026-10-29

Base: main `f9e2ccca`. This is an isolated candidate diagnostic, not a promoted baseline. Qwen itself is not blocked: LiteLLM `hosted_vllm/Qwen3.6-35B-A3B-NVFP4` at the user's configured endpoint returns native tool calls. The retained `openai/` restriction applies separately.

The original route-only run produced eight invalid outputs because the nested `issue` object arrived as a JSON string. A direct one-call LiteLLM probe reproduced this outside ADK. Adding an equivalent explicit object type to the native tool parameter made the probe validate. This is consistent with the [$ref parser bug reported upstream](https://github.com/vllm-project/vllm/issues/46924); the endpoint's exact server/parser version is unknown. A field-metadata attempt did not survive native schema generation and was reverted. The final existing accounting callback adds that existing referenced type before dispatch only on `hosted_vllm/`. Canonical output schema and response validation remain unchanged; there is no output repair.

Final configuration digest: `f95887944896f202e99b82e6b9a788c7c8941724f0d22583099fe4285bd2d374`. Intake resource digest: `0dabcb352d5b46493752ff829d96accec632a997af36feed2dde4d50c54b682b`. ADK 2.13.0 / LiteLLM 1.106.3, one repeat per cohort, episode window 60 seconds. Fixture inputs, source, inventories, oracles, dataset identities and cohort membership are unchanged from the merged main. Inventory here is frozen evaluation input, not verified current production images.

| Cohort | Exact pass | Classification correct | Invalid outputs | Operational failures | False supported |
| --- | --- | --- | --- | --- | --- |
| Original 8 | 7/8 | 8/8 | 0 | 0 | 0 |
| Scanner JSON 32 | 25/32 | 30/32 | 1 | 0 | 1 |

Actual native image comparisons: 3 original / 25 JSON. Successful skill refreshes: 1 / 5. Model calls: 11 / 58. Tokens reported: original 50,772 input / 7,421 output; JSON 285,384 / 36,248. Cost unknown. Sum of episode times: 84.16 / 374.97 seconds; no system-wide speed claim.

The original service case missed expected requirements. JSON failures include a false-supported contradictory report, one invalid multiple-issue output, missing report facts or reasons, title-only inference and an incorrect dependency execution mode. The outgoing-schema correction resolves transport conformance, not all classification defects. No held-out, repeat-stability, full live investigation or general hostile-source guarantee is claimed. Prior reports, including interrupted runs with explicit unrun rows, remain private.

Commands and final native/package gates are recorded in [PLAN-0004](../../docs/plans/archive/plans/PLAN-0004-intake-qwen-route-evaluation.md). Earlier [main integration](2026-10-28-intake-main-integration.md) reports remain exact historical records.


Final gates: 1,165 offline tests passed (133 deselected); 33 native integration/workflow/replay tests passed, including the actual live Qwen intake workflow with Docker and Temporal. Scripted investigation producer/auditor tests remain distinct from that live intake smoke. Quality gates and wheel/sdist build passed; outside-checkout installed resources loaded. The unresolved semantic defect is tracked as [ISSUE-0001](../../docs/plans/active/ISSUE-0001-intake-conflicting-reports.md). No full live investigation-chain or general scanner-quality qualification is claimed.
