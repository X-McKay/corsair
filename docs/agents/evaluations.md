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

`just eval-agent` invokes the installed module, not a retired evaluator script. The producer invocation admits an immutable local snapshot for source reads but does not run the target or arbitrary probe code on the host. The auditor invocation is private-guidance-only. Raw reports belong under ignored `.runs/`; retain sanitized baselines and experiment notes under [`evals/baselines/`](../../evals/baselines/) and [`evals/experiments/`](../../evals/experiments/).

Each frozen fixture input and oracle is read and digest-verified before use. The evaluator keeps its oracle local: it passes only the role input to the factory and compares the returned typed output outside the agent boundary. The producer diagnostic checks the exact canonical control payload and an allowed candidate payload; it is not semantic-equivalence or vulnerability-accuracy scoring. The auditor diagnostic checks its decision on the supplied source/submission packet without an observation or expected label.

A provider policy block, provider failure, malformed output, or other operational error remains an operational failure in the report. No frozen label turns into a pass after a policy block. For full investigations, the external scorer holds the oracle outside agents, tools, and workflows; it scores terminal results only after trusted evidence validation and policy processing, retaining invalid positive evidence, forbidden labels, inconclusive outcomes, and operational failures in the record.

## Earlier diagnostic evidence

The following results are intentionally small and have different scopes:

| Evidence | Result | Scope and limit |
| --- | ---: | --- |
| Isolated producer frozen development diagnostic | **3/3** | One case repeated three times; exact canonical payload matching only. |
| Isolated auditor frozen development diagnostic | **6/6** | Two cases repeated three times; semantic-review decision matching only. |
| Physical-Mac live model/worker/Docker/Temporal batch with external scorer | **2/3** | A separate composed batch. The safe case's second bounded round had an execution error and correctly remained `ERROR` / `INCONCLUSIVE`. |

The third result does not upgrade either isolated diagnostic into an end-to-end pass. Its retained limitation is documented in [ISSUE-0010](../plans/active/ISSUE-0010-live-safe-case-probe.md). That earlier local revision passed **134 tests** in the cited physical-Mac qualification; Linux amd64 was **not rerun** for that local revision. Supported targets remain macOS arm64 and Linux amd64, as described in the [platform reference](../reference/platforms.md).

No result above claims a population accuracy rate, false-positive rate, production baseline, hostile-target attestation, or automated baseline promotion. See the [baseline policy](../../evals/baselines/README.md) and [frozen experiment index](../../evals/experiments/README.md) for the evidence rules. Current work and planned follow-up are indexed in the [plans](../plans/README.md).


## Expanded candidate diagnostics

The development diagnostics above remain unchanged for comparison. The expanded producer manifest contains3 cases and auditor4 cases, including the original inputs. The4 additions are explicitly AI-authored candidate cases pending human review, not held-out human labels:

```bash
just -- eval-agent producer evals/datasets/producer-expanded.json   --settings .state/settings.json --repeats 3
just -- eval-agent auditor evals/datasets/auditor-expanded.json   --settings .state/settings.json --repeats 3
```

The corrected original freeze passed3/3 and6/6. The first expanded producer run passed4/9; its final repeat after code cleanup passed5/9, while auditor passed12/12 on both runs. Final producer failures were candidate exact-string mismatches, not malformed-output/provider failures; semantic equivalence/native validity of alternate strings remains unestablished. Keep the failures and review [ISSUE-0011](../plans/active/ISSUE-0011-expanded-producer-diagnostics.md) rather than adding oracle alternatives to obtain green scores.

The [candidate receipt](../../evals/baselines/candidates/expanded-diagnostics-2026-10-25.json) is distinct from byte-preserved test [qualification receipts](../../evals/baselines/qualifications/README.md). No baseline was promoted. Initial missing-client-key failures were retained separately; the user-selected unauthenticated endpoint uses the earlier documented non-secret EMPTY SDK field in the test process only, never as a credential fallback in runtime code. The subsequent real composed batch remained2/3, with the safe case ERROR/INCONCLUSIVE and its existing issue open.


The later publication cleanup repeat scored producer4/9 (original case3/3) and auditor12/12, with0 provider/operational failures. [Publication receipt](../../evals/baselines/qualifications/qualification-publication-2026-10-25.json) preserves it separately from the earlier5/9 repeat. Candidate exact-match failures and ISSUE-0010 remain open; fluctuating small-cohort scores are not a promoted accuracy estimate.

## Current consolidated configuration

The producer now returns canonical `ProducerDecision`, with either a proposal or explicit abstention; exact-match diagnostics classify the projection without declaring semantic equivalence. The merged-root post-cleanup expanded freeze scored producer4/9 and auditor12/12, with0 provider/operational errors. These are tiny AI-authored candidate diagnostics, not population accuracy or baseline promotion. A separate final three-case full-live batch passed3/3 (two correctly resolved, one expected inconclusive), with0 operational errors; this is not population accuracy or a passed producer diagnostic. Prior producer3/9 and live0/3 results remain retained in [ISSUE-0012](../plans/active/ISSUE-0012-producer-decision-live-quality.md). Current root/live/native counts and configuration identities belong in [current plans](../plans/README.md), not inferred from old tables.

Use [the eval skill and coding-agent workflow](../development/coding-agent-workflows.md) for the concrete iteration sequence, and [extension qualification](../guides/extensions.md) before changing recipe, language, framework or image. Keep prior reports immutable and give each comparison a separate output path.

### What the producer4/9 actually means

The saved expanded repeat has three cases repeated three times, not nine independent findings. `case01` passed3/3; `producer02` passed1/3 with two `candidate_exact_mismatch` results; `producer03` passed0/3 with two `control_mismatch` results and one `candidate_exact_mismatch`. All nine were structurally valid proposals; no provider failure or abstention occurred. Three exploit candidates were outside the frozen allowed-value list and two benign controls differed from the canonical expected control. These diagnostics compare payload values, not general security accuracy. Alternate exploit strings require separately admitted trusted native replay before calling them equivalent; do not expand the oracle to hide a failure. The distinct full-live3/3 cohort is not an override for this failed producer diagnostic.
