# Agentic intake evaluator

The executable evaluator is `corsair.evaluation.intake_agent`, packaged with Corsair. This document does not define a second scorer. The existing deterministic scanner-envelope evaluator remains `corsair.evaluation.intake`.

Run an explicitly configured isolated diagnostic from the repository root:

```bash
uv run --locked --extra providers python -m corsair.evaluation.intake_agent \
  evals/datasets/intake-capabilities.json --settings /operator/settings.json \
  --repeats 1 --seconds 60 --output .runs/intake/report.json
```

The agent receives bounded scanner JSON, source context and available-image inventory. Only the evaluator receives the oracle. Categorical scoring covers classification, surface, language, execution mode, requirements, reasons, image membership, grounded locations and retained issue facts. Every attempt stays in the denominator; configuration failures, invalid outputs, missing input and operational failures remain separate counts. `scored_attempts` counts rows with a classification score, including incorrect classifications. A configuration refusal is not a model accuracy measurement.

The eight-case original cohort and 32-case JSON candidate cohort remain separate. Candidate labels have not been promoted to a held-out baseline. The new manifest discriminator is `corsair.intake-agent-dataset/1`; main's existing `corsair.intake-dataset/1` scanner format is unchanged. Fixture bytes, declared hashes and cohort membership were retained during integration. See the [integration record](../../docs/plans/archive/plans/PLAN-0003-intake-agent-integration.md) and [intake guide](../../docs/guides/intake-agent.md) for configuration limits and executed gates.
