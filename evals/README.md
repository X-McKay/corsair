# Eval cases

The v1 suite scorers were removed with v1; the frozen case data, sets and the corpus loader remain, and v2 agents
register their suites in [`run.py`](run.py). Per-suite READMEs describe the v1 scorers that produced these cases.

Every frozen eval case is one directory, grouped by agent, language and set ([PLAN-0098](../docs/development/plans/PLAN-0098-eval-corpus-breadth.md); loader [`cases.py`](cases.py)):

```text
evals/<suite>/<language>/<set>/<case id>/
  input.json     exactly what the suite's task receives (the agent's input)
  oracle.json    evaluator-only expectations and scripted replay; never reaches the agent
  case.json      language, framework, family, kind, behaviour probed, provenance
evals/<suite>/sets/<set>.json
  {"held_out": false, "cases": {"<language>/<case id>": "<sha256 of the three files>", ...}}
```

`<suite>` is the agent's eval package: `environment`, `issue_identification`, `test_planning`, `test_authoring`, `evidence_assessment`, or `e2e` for whole-chain cases ([e2e/README.md](e2e/README.md)). `<language>` is `python`, `java`, `javascript`, `ruby`, `perl`, or `common` for a case with no language. A set's identity (`dataset_sha256` in every report) is the SHA-256 of its manifest, so it changes only when a listed case changes. Loading refuses a case whose files differ from its manifest hash.

```sh
make eval AGENT=<agent> SET=breadth                        # every language in the set
make eval AGENT=<agent> SET=breadth EVAL_LANGUAGE=ruby     # one language; baselines are kept per set and language
uv run --locked python -m evals.inventory                  # case counts per agent and language
uv run --locked python -m evals.cases test_planning breadth [--freeze]   # check or rewrite a manifest
```

A held-out set's manifest says `"held_out": true`; its case ids are never cited under `docs/development/` and it is never used for tuning ([test_evaluation_layout.py](../tests/configuration/test_evaluation_layout.py)). Adding a case means writing its directory and re-freezing that set; changing a frozen case changes the set's identity, so compare runs only within one identity. Suites that are not agent evals (`repository_identification`, `issue_analysis`, `benchmark`, `corpus`) keep their own formats; the imported corpus stays verbatim under `benchmarks/corpus/`.

## v2 agent evals

Each v2 agent keeps its eval inside its package, `src/corsair/agents/<agent>/evals/`:
`evaluate.py` (one `AgentEval` for the shared runner [`agent_eval.py`](agent_eval.py)), `README.md`,
`release-policy.yaml` (placeholder), `sets/<set>.json` and `<language>/<set>/<case>/{input,oracle,case}.json`.
The whole chain's cases live under [`e2e/`](e2e/README.md), set `v2`. Every v2 `case.json` also carries `category`
(smoke, capability, regression, adversarial, failure-mode), `expected` (the behaviour, in plain sentences) and
`dimensions` (correctness, contract, grounding, trajectory, robustness, safety). A dimension counts only on the
cases that declare it.

```text
PYTHONPATH=src:. python -m evals.run <agent> --set development                     # scripted oracle replay, no model
PYTHONPATH=src:. python -m evals.run <agent> --set development --language perl     # one language
PYTHONPATH=src:. python -m evals.run <agent> --set development --provider-config PATH   # live, one model profile per agent
```

A run writes `command.json`, `attempts.jsonl`, `receipts/`, `summary.json` (schema `corsair-eval-summary/v1`:
dimensions passed/total; `wall_s`, `requests`, `tool_calls`, `input_tokens`, `output_tokens`, `tokens` and `retries`;
the parameters each agent ran with and status counts, overall and by language and kind. Names follow the run record
`corsair-v2-run/1` ([RUN_RECORD.md](../src/corsair/RUN_RECORD.md)): a value the provider did not report is null,
never zero, and a total with an unknown in it is null; for labelled rows, the decisive rate, accuracy per label and abstention
rates by terminal reason), `policy.json` (pass, fail, unknown or not_set per policy entry; gates are deferred, so it
never changes the exit code) and `comparison.md` against the promoted baseline. A scripted run checks plumbing and
oracle consistency only; baselines come from live runs.

Live baselines run one agent after another (one live inference user at a time) on a host with the provider config
(and Docker for the chain), then a person chooses the run to keep:

```sh
make eval-live-baselines PROVIDER_CONFIG=PATH [AGENTS="grounding builder"] [NOTE=...]   # prints each run id
make baseline-commit AGENT=<agent> RUN=<run id>   # whole set, clean checkout; writes <agent evals>/baselines/<set>-<mode>.json
```

The committed file is the run's summary without per-attempt rows, plus its policy status; comparisons fall back to it
on a checkout that does not hold the run under `.runs/`.
