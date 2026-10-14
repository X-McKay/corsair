# Eval cases

Every frozen eval case is one directory, grouped by agent, language and set ([PLAN-0094](../docs/development/plans/PLAN-0094-eval-corpus-breadth.md); loader [`cases.py`](cases.py)):

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
make eval AGENT=planning SET=breadth                       # every language in the set
make eval AGENT=planning SET=breadth EVAL_LANGUAGE=ruby    # one language; baselines are kept per set and language
PYTHONPATH=src:. .venv/bin/python -m evals.inventory       # case counts per agent and language
PYTHONPATH=src:. .venv/bin/python -m evals.cases test_planning breadth [--freeze]   # check or rewrite a manifest
```

A held-out set's manifest says `"held_out": true`; its case ids are never cited under `docs/development/` and it is never used for tuning ([test_evaluation_layout.py](../tests/configuration/test_evaluation_layout.py)). Adding a case means writing its directory and re-freezing that set; changing a frozen case changes the set's identity, so compare runs only within one identity. Suites that are not agent evals (`repository_identification`, `issue_analysis`, `benchmark`, `corpus`) keep their own formats; the imported corpus stays verbatim under `benchmarks/corpus/`.
