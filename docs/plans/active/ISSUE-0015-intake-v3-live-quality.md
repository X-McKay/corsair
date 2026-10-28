# Intake and v3 live-model completion quality

Status: open, 2026-10-27. Owner: intake/producer native structured completion and evaluation. This is separate from [the legacy Node/Java quality issue](ISSUE-0014-node-java-assessment-live-quality.md).

## Measured boundary

User-approved synthetic diagnostics used `openai/Qwen3.6-35B-A3B-NVFP4` through the native LiteLLM/OpenAI-compatible route at `https://llm.almckay.io/v1`. Provider, model, inputs, external oracles, native schemas and reviewed execution permissions were unchanged for the approved continuation. Sequential runs avoided competing requests within this evaluation. Costs and unreported usage remain unknown.

| Gate | Result | Meaning |
| --- | --- | --- |
| Intake, eight frozen candidate cases | 1/8 exact; 2/8 correct classification; 2 invalid outputs; 0 false-supported | Genuine ADK plus real inspection Docker, with frozen hypothetical inventories. Does not establish reliable classification or physical image admission. |
| Independent producer/auditor, four frozen cases | 3/4 exact | Auditor matched all three labels in this single repeat. Producer failed without a valid plan after reporting 4,096 output tokens, the configured limit. |
| Full model/Temporal/Docker chain attempt | INCOMPLETE, producer OUTPUT_INVALID | Result recording succeeded; neither audit nor generated-test execution was reached. This is not a successful full live-chain qualification. |

The authored cohorts are pending human review, not held-out baselines. Earlier 2/4 role reports, failed/incomplete intake runs and blocked attempts remain retained. No causal quality improvement, accuracy threshold or baseline promotion is claimed.

## Failure classes

Intake missed expected supported cases through unknown requirements or insufficient context and misread some absent-image cases as missing issue information. Two outputs failed the canonical schema. The supported-class recall was 0/3 in this cohort; the zero false-supported count does not establish safety or useful recall. The out-of-scope case was the sole exact intake pass.

The producer has both invalid-output and model-failure examples across preserved runs. The approved isolated repeat reported the configured output-token limit, while the full-chain attempt failed structured completion after one model call. These observations do not identify one proven root cause; token budgeting and provider/schema conformance need separate diagnosis. Keep categorical diagnostics and input/resource identities separate from raw private model output.

## Next qualification work

Diagnose native provider/schema completion and intake source-context/category fidelity with unchanged frozen cases before altering prompts, budgets or model settings. Any change gets a new configuration/resource identity and affected native plus independent role evaluation. Preserve invalid output and operational failures in denominators. Human review and family-grouped held-out repeats remain required before reliability claims.

Do not repair model-authored JSON strings, relabel oracles to make outputs pass, restore recipes as a support gate, weaken sandbox permissions, or interpret generated test success as a vulnerability oracle. Security assessment remains UNRESOLVED.

See [implementation and executed commands](PLAN-0133-recipe-free-implementation.md) and [the current guide](../../guides/investigations.md). Raw immutable artifacts and reports remain in ignored `.runs/`.


## Intake follow-up, 2026-10-28

[PLAN-0134](PLAN-0134-intake-quality.md) preserves a fresh control (0/8 exact, 3/8 correct decisions), a structure-only variant (1/8 exact, 3/8 correct decisions), and the final reviewed guidance over two unchanged repeats (**14/16 exact, 16/16 correct decisions, zero invalid outputs or false-supported**). Repeat exact scores were 6/8 and 8/8. Remaining mismatches concerned surface and execution-mode labels. Native schema bytes, cases, external labels, provider/model, settings and budgets were unchanged; resources have distinct recorded identities.

This improves the authored intake diagnostic; it does not close this issue. Human-reviewed held-out and additional repeat evidence remain pending, and the producer/full-chain failures above were not changed or rerun by the intake-only work. See the [sanitized experiment](../../../evals/experiments/2026-10-28-intake-quality.md) for separate native and model boundaries.

## Scanner/image-tool and pipeline follow-up, 2026-10-28

The [image-selection experiment](../../../evals/experiments/2026-10-28-intake-image-selection.md) preserves 46/64 scanner exact matches, 57/64 correct decisions and one false-supported; the separate original run had invalid output and a model failure. All live episodes ignored optional tools. A later final original-eight repeat scored 5/8 exact, 8/8 correct decisions and no invalid/failure/false-supported outcomes; it still made no actual tool calls. These authored, correlated candidate runs do not establish held-out reliability.

[The v4 pipeline attempt](../../../evals/experiments/2026-10-28-intake-pipeline.md) ran actual intake with real Temporal/Docker and recorded `stopped / UNSUPPORTED`: the model omitted an available Python image. Producer/auditor/generated-test execution were correctly not scheduled. Scripted native tests prove selected non-default image routing and categorical stopping; successful full live execution and role reliability remain open. No baseline promotion or security conclusion is authorized by these results.
