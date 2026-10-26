# Agent evaluations

Agent evaluation has three distinct levels. Keep their evidence separate: a deterministic native-ADK test, an isolated live-model fixture evaluation, and a composed Docker/Temporal investigation answer different questions.

| Level | What runs | What it establishes | What it does not establish |
| --- | --- | --- | --- |
| Native test double | Tests use `ScriptedLlm`, a deterministic implementation of ADK's `BaseLlm`, with the real ADK runner/factories. | Factory wiring, schema/tool behavior, callback budgets, and SDK fallback regressions. | Provider behavior, target execution, or model accuracy. |
| Isolated agent evaluation | The installed `corsair.evaluation.agents` module calls the production factory and native runner against a frozen input with an explicitly configured live model. | A role's bounded output against its frozen diagnostic oracle. | Docker execution, Temporal durability, hostile-target resistance, or whole-system accuracy. |
| Composed evaluation | A worker, ordinary Temporal workflow, trusted Docker observer, immutable artifacts, policy, and external scorer process a frozen dataset. | The specified end-to-end cohort, including evidence validity and operational failures. | Population-level accuracy, production readiness, or universal target integrity. |

## Run isolated checks

Run these repository-root commands only with a deliberately selected settings file and the required provider configuration in the worker environment:

```bash
just -- eval-agent producer evals/datasets/producer-dev.json \
  --settings /path/to/settings.json --repeats 3
just -- eval-agent auditor evals/datasets/auditor-dev.json \
  --settings /path/to/settings.json --repeats 3
```

`just eval-agent` invokes the installed module. The producer invocation admits an immutable local snapshot for source reads but does not run the target or any probe code on the host. The auditor invocation has no tools. Raw reports belong under ignored `.runs/`; retain sanitized baselines and experiment notes under [`evals/baselines/`](../../evals/baselines/) and [`evals/experiments/`](../../evals/experiments/).

Each frozen fixture input and oracle is read and digest-verified before use. The evaluator keeps its oracle local: it passes only the role input to the factory and compares the returned typed output outside the agent boundary. The producer diagnostic checks the exact canonical control payload and an allowed candidate payload; it is not semantic-equivalence or vulnerability-accuracy scoring. The auditor diagnostic checks its decision on the supplied source/submission packet without an observation or expected label. The auditor's rubric names its rules `R1` mechanism, `R2` differential, `R3` production logic and `R4` disclosure, not echo; each auditor row records the returned `audit_decision` and the decisive `audit_rule` (`ALL` for an acceptance) so a rejection is attributable. The rule is model output: it is reported, never scored, and the pass predicate stays the decision alone.

A provider policy block, provider failure, malformed output, or other operational error remains an operational failure in the report. No frozen label turns into a pass after a policy block. For full investigations, the external scorer holds the oracle outside agents, tools, and workflows; it scores terminal results only after trusted evidence validation and policy processing, retaining invalid positive evidence, forbidden labels, inconclusive outcomes, and operational failures in the record.

## Reading results

Isolated diagnostics compare payload values and audit decisions against frozen oracles; they are not population accuracy, a false-positive rate, hostile-target attestation, or automated baseline promotion. A composed live batch is scored externally on the six labels and retains invalid positive evidence, forbidden labels, inconclusive outcomes, and operational failures. Neither kind of result upgrades the other.

Each composed-batch row also carries a `gate_ledger`: one entry per recorded round (`session`, `round`, `stage`, `gate`, `reason`) naming what stopped it, followed by any case-level `policy` stop such as `budget_exhausted`, `negative_threshold_unmet`, `fix_not_blocked` or `execution_error`. Stages are `producer` (adapter gates such as `producer_invalid:llm_budget` or `provider_permanent`, and `producer_abstained`), `evidence` (the evidence feedback gate, `probe_invalid`), `audit` (`audit_reject`, `audit_invalid:*`, `audit_insufficient_context`, when an otherwise decisive pair was not accepted) and `kernel` (`coverage`, `no_differential`, `target_unbound`, `clean_negative`, `demonstrated`). The [ledger](../../src/corsair/evaluation/ledger.py) is derived by the external scorer from the recorded result and each round's own validated receipts; a round whose receipts do not validate is `evidence_unverified`. It describes the kernel's decision and never makes one. The report summary adds `gate_ledger` (counts of every entry) and `failure_stops` (counts of each failed row's final entry), and `corsair report` renders both as tables, so the dominant loss is read from the report rather than reconstructed by hand.

The expanded datasets (`producer-expanded.json`, `auditor-expanded.json`) add AI-authored candidate cases pending human review; they are not held-out human labels. A candidate exact-string mismatch is a retained failure, not a reason to widen the oracle: alternate payloads require separately admitted trusted native replay before being called equivalent.

## Comparing two runs

Compare two saved reports on the same frozen dataset with `corsair compare BASELINE.json CANDIDATE.json` (see the [CLI reference](../reference/cli.md#compare-baselinejson-candidatejson)). It joins attempts by case and repeat, flags pass/fail flips, label changes and new forbidden labels, and reports usage deltas; it exits `1` on a regression. It refuses reports whose dataset digests differ or are undeclared unless `--allow-dataset-mismatch` is passed, and then marks the result as a mismatch. Report the dataset digest, the cohort of each side and any configuration digest change with the comparison. A comparison of two isolated diagnostics remains a role-level diagnostic, and a candidate with no regression on one frozen cohort is not a promoted baseline.

## Families and splits

A family is one vulnerability class in one target: both variants of a chain pair and any adversarial row built on them. Promotion needs family-grouped held-out data, so a family must appear in exactly one split. `just dataset-families` checks every manifest under `evals/datasets/` (or the manifests given) and exits `1` when a family, a case or a chain pair crosses splits, or when a pair's variants carry different families; [`evaluation/families.py`](../../src/corsair/evaluation/families.py) exposes the same check as `check_family_splits(paths)` for a dataset validator. Composed report rows carry their `family` and `split`; `corsair report --families` adds per-family and per-split attempts, pass rate, decisive count, forbidden labels and operational failures, and `corsair compare --families` adds each family's deltas and attributed regressions. These views group already-scored rows and never re-score; a family's pass rate on a small frozen cohort is a diagnostic, not a class-level accuracy claim.

See the [baseline policy](../../evals/baselines/README.md) and [frozen experiment index](../../evals/experiments/README.md) for the evidence rules, and [current plans](../plans/README.md) for the open decisions that affect evaluation. Use [the eval skill and coding-agent workflow](../development/coding-agent-workflows.md) for the concrete iteration sequence, and [extension qualification](../guides/extensions.md) before changing recipe, language, framework or image. Keep prior reports immutable and give each comparison a separate output path.
