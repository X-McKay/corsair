# Agentic image-selection capability, 2026-10-28

Status: implemented capability, live model reliability unqualified. See [PLAN-0136](../../docs/plans/active/PLAN-0136-intake-image-tool.md) and the preceding [scanner diagnostic](2026-10-28-intake-json.md).

The user requested an agent tool and skill instead of automatic final image choice. Intake now exposes `compare_images`, bound to a detached snapshot of currently available reviewed images. It reports capability matches and missing requirements; uncertainty and forbidden network/privilege requirements never produce a compatible row. The agent reasons about source and edge cases, then chooses an exact reference or retains categorical blockers. Trusted policy and immutable image rechecks are unchanged. No image discovery/pull/build, execution, provider or permission was added by the helper.

The `image-selection` procedure is loaded from the built package through native ADK, preloaded into the episode and available through private native refresh tools. Existing call, time and output budgets remain. Tool/helper and raw skill resources enter the distinct intake identity; no case IDs or fixture-specific answers enter instructions.

## Frozen live results

Same 32-case scanner cohort revision 2, model/provider, input/source/inventory/oracle bytes, scorer and 60-second episode ceilings; two repetitions. Original eight cases remain separate.

| Variant/cohort | Exact | Correct decisions | False-supported | Invalid outputs | Model failures |
| --- | --- | --- | --- | --- | --- |
| Scanner baseline | 38/64 | 48/64 | 4 | 0 | 3 |
| Scanner prompt only | 39/64 | 52/64 | 2 | 0 | 3 |
| Scanner tool + skill | 46/64 | 57/64 | 1 | 0 | 0 |
| Original cohort, tool + skill | 4/8 | 6/8 | 0 | 1 | 1 |

The skill was actually preloaded in all 72 new episodes, but the live model requested **zero tools**. Therefore no benefit from tool invocation is established. The original cohort's invalid output/model failure is retained; the scanner improvement is descriptive on related authored cases, not an overall reliability or causal skill/tool claim. Repeats on human-reviewed held-out source families and real redacted scanner exports remain pending.

Tool/skill resource identity: `e11cf4391d94e68a9e9caaa306c43fb134e3de58f03e58ece626bc2ca6f12ce3`. Private complete reports: `.runs/intake-json-20261028/original-image-tool.json` and `image-tool-v2.json`; all prior reports remain retained. Genuine ADK and real inspection Docker used frozen hypothetical inventories, not physical image-admission qualification. Missing costs remain unknown.

## Native evidence and remaining work

Eleven direct/helper/native regressions failed before implementation. Positive and empty inventory, unknown and missing requirements, denied network/privileges, malformed profiles, detached state and output overflow are tested. Genuine scripted ADK exercises both schema/tool paths, actual skill refresh and helper calls, positive image selection and loader budgets. These are conformance checks, not live-model use. Package and full gate commands/results are recorded in the plan.

The subsequent [end-to-end handoff](../../docs/plans/active/PLAN-0137-intake-investigation-handoff.md) must stop negative/unresolved intake decisions and bind the accepted immutable image to generated-test execution. Workflow wiring cannot make the remaining false-supported model classifications correct. Security assessment remains `UNRESOLVED`; no baseline, publication or production-readiness promotion occurred.
