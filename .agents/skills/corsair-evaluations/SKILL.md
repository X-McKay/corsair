---
name: corsair-evaluations
description: Run and interpret Corsair's frozen agent and composed evaluations without changing evidence boundaries or promoting results. Use for evaluation design, isolated producer or auditor diagnostics, cohort expansion, provider-configured repeats, and recording native, Docker, Temporal, or live-model results.
---

# Corsair evaluation workflow

Use this workflow to improve or run a stated evaluation boundary. Treat it as maintainer guidance only; it does not inject runtime skills, tools, credentials, or publication authority.

## Freeze the question and cohort

1. Read [agent evaluations](../../../docs/agents/evaluations.md), [development testing](../../../docs/development/testing.md), [extension qualification](../../../docs/guides/extensions.md), and the [baseline policy](../../../evals/baselines/README.md) before changing an evaluator, fixture, dataset, prompt, model setting, or report.
2. State one hypothesis and one measured boundary. Keep the input bytes, declared hashes, external labels/oracles, source/image/instruction/tool/schema/budget identity, and cohort membership frozen for a repeat. Do not edit an oracle, fixture, allowed candidate, or denominator to convert a failure into a pass.
3. Keep the original frozen cohort, expanded candidate cohort, and safety or composed cohort separate. Report their membership and results separately; candidate cases remain pending human review and are not held-out or promoted baselines.
4. Retain the full denominator: exact matches, mismatches and match kinds, abstentions, malformed outputs, provider/configuration failures, unavailable rows, unexpected exceptions, and uncertain outcomes. Exact-match diagnostics are not semantic-equivalence, vulnerability-accuracy, or negative-clearance measurements.

## Run independently and explicitly

1. Evaluate producer and auditor with their independent production factories and native ADK runner. Keep labels and oracles evaluator-owned and outside agent, tool, and workflow packets; do not make a role validate its own answer or create factual evidence.
2. Select provider, model, settings file, repeats, and budgets explicitly. Never add a credential fallback, relax a policy block, or substitute a different provider silently. Keep configuration, risk, model, runtime, source, image, prompt, and schema identity in the resulting record; record missing usage or cost as unknown.
3. Use the repository-root isolated commands only when the operator has deliberately configured the required provider environment:

   ```bash
   just -- eval-agent producer evals/datasets/producer-dev.json \
     --settings /operator/settings.json --repeats 3
   just -- eval-agent auditor evals/datasets/auditor-dev.json \
     --settings /operator/settings.json --repeats 3
   ```

4. Run the quality and offline checks around evaluator changes:

   ```bash
   just check
   just -- test -q -W error
   ```

   Preserve raw reports in ignored `.runs/` and retain only appropriate sanitized records under `evals/baselines/` or `evals/experiments/`.

5. For the improvement loop's rig step, prefer the recording recipes, which refuse without a named connector and its provider environment, and leave a raw report, a sanitised `identity.json`, the `corsair compare` result and a README draft under `.runs/live/` (see [recording a live run](../../../docs/agents/evaluations.md#recording-a-live-run-in-one-step)). Run `--dry-run` first; review the draft and resolve its TODOs before copying a record under `evals/baselines/candidates/`:

   ```bash
   just -- live-agent auditor evals/datasets/auditor-dev.json BASELINE.json --dry-run
   just -- live-chain evals/datasets/dev.json BASELINE.json
   ```

## Keep qualification levels separate

1. Label a deterministic native-ADK test as factory and schema coverage only. It does not establish provider behavior, target execution, or model accuracy.
2. Label an isolated live-model fixture run as a role-level frozen diagnostic only. It does not establish Docker execution, Temporal durability, hostile-target resistance, or whole-system accuracy.
3. Label a composed evaluation only after the stated worker, real provider, Docker observer, ordinary Temporal workflow, immutable evidence, policy processing, and external scorer have actually run. Preserve Docker, Temporal, provider, evidence, cleanup, and scorer failures rather than collapsing them into an abstention or pass.
4. Do not promote a baseline, change a safety policy, close an issue, publish a result, or claim an accuracy/security threshold on the agent's authority. Promotion requires the human-reviewed frozen, human-labelled, family-grouped held-out data and repeat evidence required by the baseline policy.
