# Gates, CI and release policy for v2

Status: **CI enabled on develop** (2026-10-14, Al's go on PR #162). Release policies stay `enforced: false` until
the build owner commits live baselines and the thresholds are adopted, so `release-check` toward main fails until
then. Architecture and the deferral itself:
[SPEC-0082](../development/specs/SPEC-0082-corsair-v2-architecture.md#acceptance-and-validation).

## Rules that do not change

- CI never calls a model. Every CI job is offline and deterministic. Live per-agent baselines and live chain runs
  run on the operator host (one live inference user at a time) and reach CI only as committed baseline files.
- The order of error costs decides every threshold: a false LIKELY_NOT_EXPLOITABLE first, the inconclusive rate
  second, cost and latency last (SPEC-0082).
- An unobserved metric, missing provenance or unset threshold is unknown, and unknown never passes.
- Release policies are operator-owned. Tools report and propose; only a person edits a policy.
- No gate branches on language, framework, CWE, case id, repository or fixture. Language appears only as a rollup key.

## The enabling gate

Gates, full CI and release policies return when `make gate-status` exits 0. That command reads only committed files:

1. Every agent (Grounding, Investigator, Builder, Control Prober, Exploit Prober, Reviewer) has an eval suite and a
   committed live baseline for the set its release policy names.
2. The chain's committed live baseline gets both directions right in at least three languages. For each counted
   language, at least one case is expected LIKELY_EXPLOITABLE, is labelled so, and has the correct fix result on the
   fixed revision. At least one other case is expected LIKELY_NOT_EXPLOITABLE and is labelled so. Language-free
   (`common`) cases do not count. The gate reads the per-language dispositions in the committed baseline; a correct
   LIKELY_EXPLOITABLE label already requires the differential result on the fixed revision (D12, rule R4).

Today it reports 0 of 6 agent baselines and 0 of 3 languages.

## CI when enabled (`.github/workflows/development.yml`)

| Job | Runs on | What it proves |
| --- | --- | --- |
| `offline-guards` | every PR and push | `make test-v2`: contracts, rules, outcome table, scripted agent and chain evals, record and workflow guards. Keeps the existing check name |
| `scripted-evals (<agent>)` | every PR and push | `make eval AGENT=<agent>` for each agent with a suite and the chain, through the real eval runner (summary, comparison, policy verdict in the job summary). A scripted eval failure fails the job |
| `runtime-row (<row>)` | PRs touching images, the matrix, framework skills, workspace or execution; pushes to develop and main; nightly | Per matrix row: rebuild the image from `deploy/qualification/toolchains/<dir>`, require the row's exact tag, classify both canaries (`tools/v2_canary.py`), then run the offline suite with the image present so Docker-backed tests run |
| `release-check` | PRs into main, pushes to main | `make release-check` over committed live baselines and enforced policies |

The toolchain image workflow stays manual (`toolchain-images.yml`); `runtime-row` replaces its PR trigger. The
kind/OpenShell gate stays a milestone gate on the operator host, run when Al calls it; it flips matrix rows from
`image-only` to `live` and is the only route to `live`.

## Release policy

Each agent's `evals/release-policy.yaml` and the chain's `evals/e2e/release-policy.yaml` gain `enforced`. While it
is `false` (today), `make eval` reports the verdict without changing its exit code. When `true`, an in-scope live run
whose verdict is not `pass` exits 1.

`make release-check` (`tools/release_check.py check`) passes an agent only when all of these hold:

- The committed baseline `<eval root>/baselines/<set>-live.json` exists. It is the promoted run's `summary.json`
  without per-attempt rows, written by `make baseline-commit AGENT= RUN=` (`evals/run.py --commit-baseline`).
- The baseline is a whole-set live run.
- The baseline measured the agent as it stands. Every identity key its eval spec records must match: prompt version,
  config version, skill digest, toolset digest and, for the chain, evaluator version, review limit and matrix digest.
  The dataset digest must match too. A prompt, skill or tool change therefore needs a fresh live baseline before
  release.
- The policy is enforced, every entry passes, every threshold is set, and required provenance is present.

Hard gates stay fixed: contract rate 1.0, zero safety failures, zero exhausted budgets. For empirical thresholds,
`tools/release_check.py propose <agent>` prints suggested values from the committed baseline. A person copies the
values they accept.

## Turning it on

1. Wait for the gate: the build owner runs live baselines and live chain cases, then promotes and commits them.
   `make gate-status` must exit 0.
2. For each agent and the chain, run `propose`. Adopt the accepted thresholds, set `applies_to.sets` and set
   `enforced: true`.
3. Run `make release-check` locally until it passes.
4. Merge this PR. Then add the new required checks to branch protection (decision G3).

## Decisions for Al

- **G1, where `release-check` blocks.** Recommended: only on PRs into main and pushes to main, so develop stays fast
  and a release carries fresh baselines. The alternative is every PR into develop, which means any prompt or skill
  change carries a live baseline in the same PR.
- **G2, threshold margins.** `propose` defaults to the baseline accuracy minus 0.05 (absolute), and to p90 latency,
  mean tokens, p90 requests and p90 tool calls plus 25 percent. Hard gates are never derived from a measurement. Al
  may pick other margins, or require the false LIKELY_NOT_EXPLOITABLE rate to be zero on the chain (recommended,
  given the error-cost order).
- **G3, required checks.** Recommended branch protection on develop is `offline-guards` and every
  `scripted-evals (*)`, with `runtime-row (*)` required when it runs. On main, add `release-check`.
- **G4, reading of "both directions".** As implemented: a correct exploitable label (which already carries the
  differential result on the fixed revision), plus a correct not-exploitable label, in the same language. Al may want a stricter reading, such as the same case pair on
  both revisions or more than one pair per language.
- **G5, chain identity.** The chain baseline's identity covers its evaluator, review limit and matrix. Each agent's
  identity is checked on that agent's own baseline, not on the chain's. A stricter rule would also stale the chain
  baseline when any agent changes.

## Blockers found while preparing

- Resolved by PR #166 (611f52a): both Maven rows now name the images their sources build, and the `node22` image
  source is back on develop, so every row's tag is reproducible from source.
- The Reviewer eval suite landed with PR #165 (157 cases) and joins the `scripted-evals` matrix;
  `tests/v2/test_workflows.py` keeps the matrix in step with the agents that have a suite.
- `tests/v2/test_workspace_docker.py` pinned a Python tag that no longer matched the source. It now reads the
  matrix's Python row, so CI can build the image and run the conformance suite.
