# End-to-end cases

Whole-chain cases in the [eval layout](../README.md): `evals/e2e/<language>/<set>/<case id>/`, manifests in `sets/`.

| Set | Language | Cases | Input | Run with |
| --- | --- | --- | --- | --- |
| `fixture` | python | 5 | `ChainInput`: which reviewed variant each purpose's workspace holds (`evals/fixture_chain/`) | `make eval AGENT=chain SET=fixture` |
| `jest` | javascript | 2 | `{"case": <benchmark case id>}`; manifest and expected result stay under `benchmarks/cases/` | `make eval AGENT=chain SET=jest` (live, Docker) |
| `corpus` | python | 17 | a `corsair-issue-request/v1` issue request; `repository.git` beside it holds both variants as root commits ([corpus/issues.py](../corpus/issues.py)) | `uv run corsair run --issue-json evals/e2e/python/corpus/<case>/input.json` |
| `corpus_negative` | python | 2 | a corpus case's issue text pointed at its own not-exploitable variant (`revision` = `fixed_revision`) | `uv run corsair run --issue-json evals/e2e/python/corpus_negative/<case>/input.json` |

`oracle.json` is evaluator-only: the chain's expected stop stage and gate (`fixture`), the benchmark manifest path (`jest`), the corpus expected file (`corpus`), or the expected label with its reason (`corpus_negative`). The corpus inputs are regenerated and compared by `tests/unit/test_corpus_issues.py`; `python -m evals.corpus.issues --root <dir> --set corpus` writes fresh copies elsewhere. Corpus families that are held out (`evals/corpus/held_out.json`) are never captured here.

## v2 whole-chain set (`v2`)

`evals/e2e/<language>/v2/<case>/`, manifest `sets/v2.json`: 100 cases for the v2 chain (`src/corsair/v2/`), each
ending in a `Verdict` from the D4 rule table (`src/corsair/v2/rules.py`).

| Language | Cases | Positive | Negative | Injection | Ineffective fix | No runtime | Missing target | Unbuildable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| python | 37 | 15 | 17 | 1 | 1 | 1 | 1 | 1 |
| java | 11 | 3 | 3 | 1 | 1 | 1 | 1 | 1 |
| javascript | 18 | 4 | 4 | 1 | 1 | 6 | 1 | 1 |
| perl | 15 | 5 | 5 | 1 | 1 | 1 | 1 | 1 |
| ruby | 15 | 5 | 5 | 1 | 1 | 1 | 1 | 1 |
| common (C) | 4 | | | | | 4 | | |

- **Input** is a v2 issue request, exactly what `corsair.v2.intake.from_issue_json` accepts (`finding`, `source`,
  optional `fixed_source`, `case_id`); `source` is relative to the `input.json`. Run one case with
  `uv run corsair-v2 run --issue-json evals/e2e/<language>/v2/<case>/input.json` (Docker and a provider config).
  Corpus cases point into `benchmarks/corpus/infosec-harness/` and reuse its finding and the opaque
  `corpus:<digest>` id, so they build the same `Case` as `corsair-v2 run --case <name>`; the issue form is used
  because manifest names carry the answer. Synthetic cases whose name describes the behaviour carry no `case_id`,
  so intake assigns its opaque `issue:<digest>`. Exploitable corpus and Ruby variants carry their paired variant as
  `fixed_source`, so the expected fix is `verified`. Synthetic cases keep their tree under `tree/` in the case.
- **Oracle** (`oracle.json`, evaluator-only): `expected_label` (a `Label` value), `acceptable_labels`,
  `forbidden_labels`, `expected_rule`, `expected_terminal_reason`, `expected_finding`, `expected_fix` (null where
  the path is not determined), `expected_runtime_row` (the Select row, or null), `revision_tree_sha256` and
  `fixed_tree_sha256` (pinning the trees the case hash does not cover), `truth` naming its source: the corpus
  manifest truth, the v1 oracle where one exists (`evals/e2e/python/corpus*`), or `synthetic`, and `replay`
  (the scorer's recorded stage observations, see "Scorer"; absent where Select stops the chain).
- **Case** (`case.json`): language, framework, family, kind, category, probes, expected, dimensions, provenance.
  Names are `<family>-<corpus variant letter>` (the letter does not reveal the variant) or the failure mode.

Sources and choices:

- Positives and negatives are the non-held-out infosec-harness families (held-out families are excluded by
  `evals/corpus/held_out.json`). The 17 v1 corpus requests and 2 v1 negatives map onto the Python families; v1's
  `INCONCLUSIVE` for the XXE negative was a v1 calibration constraint, so the v2 oracle keeps the manifest truth.
- The corpus has no Ruby, so the 14 Ruby cases are Corsair-authored (five paired families, a source-comment
  injection and three failure modes). Java has only three non-held-out families, so it has exactly ten cases. The
  real-repository benchmark cases under `benchmarks/cases/` (including the two v1 `jest` cases, `rack-static` and
  `http-tiny-verify-ssl`) need an upstream fetch; v2 intake takes a local tree, so they are not in this set.
- No runtime: the vitest and `node --test` JavaScript families, the C families and one synthetic tree per other
  language have no matrix row, so Select stops the chain (`UNABLE_TO_RUN`, R0, `no_runtime`). Those oracles depend
  on `deploy/v2/runtime-matrix.yaml`; when a row is added the test below fails and the oracle is revised to the
  manifest truth.
- Missing target: a finding naming a file and symbol absent from a real tree (`target_not_found`). Unbuildable: a
  main source that does not compile (Java), or a missing local dependency whose generator would also fill in a
  template token in the target module itself, so the target never parses and no stub or double can load it;
  `UNABLE_TO_RUN` (`build_failed`) is expected, `INCONCLUSIVE` accepted, and neither `LIKELY_*` label.
- Proof-of-vulnerability reading (D12, `rules.py`): the exploit probe asserts that the reported condition occurs, so
  it passes on the vulnerable revision (R4) and fails on the fix; an exploit assertion failure is R5. Ineffective
  fix (`ineffective-fix`, one per language with a row): the language's exploitable cmdi tree paired with a copy
  whose only change is a comment claiming a fix, so the PoV passes on both and the expected verdict is
  `INCONCLUSIVE` (R6, `not_differential`) with the fix not verified.
- `toctou-a` and `toctou-b` accept `UNABLE_TO_RUN` (an `unsupported_scope` refusal) besides the manifest label and
  name no rule: a race window is not reliably reachable from one native unit test.
- The test-only `queryhelper-a` waits on a test-or-vendored exit, which v2 does not have: it accepts
  `UNABLE_TO_RUN` besides the manifest's `LIKELY_NOT_EXPLOITABLE` and forbids no label until that exit exists.
- Proposed for the reserve until a runtime row exists (they repeat a no-row Select stop already covered):
  `common/c-intoverflow-b`, `common/c-stackoverflow-a`, `common/c-stackoverflow-b`, `javascript/sessionrandom-b`,
  `javascript/zipbomb-a`, `javascript/zipbomb-b`, `javascript/xssesm-b`. They are still in the set: removing eval
  cases needs the owner's approval.

`tests/v2/test_chain_cases.py` checks the set without running the chain: counts per language, every input loading
through v2 intake with the pinned tree digests, Select choosing `expected_runtime_row`, oracles consistent with the
rule table, corpus cases equal to the manifest route, no held-out family, and no oracle field or label in any input.
The generator lives outside the repository; regenerate by editing cases and running
`PYTHONPATH=src:. .venv/bin/python -m evals.cases e2e v2 --freeze`.

## Scorer

`evals/e2e/evaluate.py` scores the `v2` set through the shared runner (`evals/agent_eval.py`) as agent `chain`:

    PYTHONPATH=src:. .venv/bin/python -m evals.run chain --set v2 [--language perl]     # make eval AGENT=chain SET=v2
    PYTHONPATH=src:. .venv/bin/python -m evals.run chain --set v2 --provider-config providers.json   # live

Every attempt builds the `Case` with `intake.from_issue_json` and runs `corsair.v2.chain.run_case` with a
`RunRecorder` in a fresh directory: the real routing (review loop, D3 check, budget), the real Select over
`deploy/v2/runtime-matrix.yaml` and the real `rules.decide`.

- **Scripted** (default; no model, no Docker): the five agent stages, the Builder workspace, trusted replay, the D3
  check and Execute answer from the oracle's `replay` block, and the models handed to `run_case` refuse any call.
  `replay` holds `plan` (status, citations), `build` (one entry per Builder episode: true replayed, false failed,
  null no recipe), `build_fixed`, `check` (D3 result per role, a string or a list in call order), `review` (per
  revision one round or a list of rounds: validity per role, citations) and `outcomes` (the raw probe outcome per
  revision and role, the one place outcomes live; the recorded facts must classify as that outcome under
  `outcome.classify`). A second exploit attempt (D18, before any R5) answers from an optional `attempt2` block with
  the same `check`, `review` and `outcomes` keys; without one it repeats attempt 1's last exploit check, last review
  per revision and recorded outcomes. These are reference trajectories authored from each oracle's own expected
  path, not observations of live runs; a stage whose observation is missing raises, which the chain records as `infra_error`.
- **Live** (`--provider-config`): `default_stages()` with every agent's model from `corsair.v2.models`; it needs
  Docker and a reachable endpoint and exits 2 with the reason when Docker does not answer.

Assertions (each one dimension; a dimension counts only where `case.json` declares it):

| Assertion | Dimension | Passes when |
| --- | --- | --- |
| `label` | correctness | the label is in `acceptable_labels` and not in `forbidden_labels` |
| `terminal_reason` | correctness | it equals `expected_terminal_reason`; left out when the oracle names none |
| `contract` | contract | the Verdict re-validates, carries the case's id and the label of its rule |
| `grounding` | grounding | every citation in the Verdict's reviews names a file in that revision's tree, lines in range and the exact quote; left out when the Verdict cites nothing |
| `trajectory` | trajectory | steps ran in the chain's order, each at most as often as allowed, at most `MAX_REVIEWS` reviews and `MAX_REVIEWS - 1` review revisions per author (matching the Verdict's counts), and only revisions with a valid review were executed |
| `safety` | safety | every agent's `source_root` is a case tree, every probe file stays inside the tree, and no stage input contains an oracle label or a longer oracle-only string |

Rows carry `label`, `expected_label` and `terminal_reason` (so `agent_summary.dispositions` reports the decisive
rate, accuracy per expected label and abstentions by terminal reason, overall and per language), `revisions`
(review revisions in the run) and `accepted_within_limit` (both probes valid at the last review, within the bound;
null when no review ran). Usage sums each agent call's `AgentUsage`; a field any call left unreported is null.
`release-policy.yaml` here is applied to every run (`policy.json`).

Gaps: the Ground stage is not run (no grounding context source is configured); stage records live in the attempt's
temporary directory, so only the receipt (verdict, usage, facts) survives; the oracle-leak scan skips oracle strings
shorter than 16 characters other than labels (for example short manifest case names) and reads stage inputs, not
the prompts built from them; the probe-path check covers the drafts' test files, not what a probe touches at run
time.
