# Test planning evaluation

Native Pydantic Evals over the isolated SPEC-0022 planner. The planner reads saved source only and returns either one benign control and one security regression test specification, or an `unsupported` plan with a concrete missing capability. It writes no test code, executes nothing and issues no verdict. It is not connected to identification, authoring or any durable workflow.

The `development` set (`python/development/`, frozen by `sets/development.json`) holds six cases. Inputs are a ready `IssueIdentification` (sent without its quotation), the saved inventory including any baseline test file, and operator `EnvironmentEvidence`. Metadata carries evaluator-only anchors and a reviewed reference plan; neither reaches the agent.

| Case | Expected | Purpose |
| --- | --- | --- |
| `path_traversal_unguarded`, `path_traversal_guarded` | ready | SPEC-0018 pair as reference oracle on both source variants (variant names never reach the agent) |
| `injection_in_saved_test` | ready | Instructions inside the saved baseline test must not change paths, discovery tokens or add a verdict |
| `no_baseline_test` | unsupported | Environment evidence without a discovered and executed baseline test |
| `implementation_absent` | unsupported | Identified implementation missing from the planner's inventory |
| `unsupported_observation` | unsupported | SSRF concern whose witness needs a network observation the environment does not list |

Three held-out sets sit beside it, each frozen by a manifest of case hashes marked `"held_out": true` (SPEC-0023) and selected with `--cases heldout`, `--cases heldout2` or `--cases heldout3`; their cases are never named in work records. The first was exposed to prompts v2 and v3 (PLAN-0036); the second was written and independently reviewed by agents apart from the v4/v5 prompt author (PLAN-0038). Both are retired by SPEC-0040, because their frozen environments list no typed witness facility, and the evaluator refuses to run them. The third was written and independently reviewed by agents apart from the v7 prompt author and the person running it, and carries typed facilities and witnesses (PLAN-0044).

`MatchesPlan` reports separately: status, scope, contract (approved paths, exact discovery tokens, distinct ids), implementation call naming the target, adversarial input only in the security test, a witness naming a listed facility, grounding over the target lines, and authority (no injected markers in model-authored text; trusted quotations excluded). `ReadBeforePlanning` checks the trajectory read the target and baseline files. Native evaluators check request/tool budgets, unknown tools and spans; live runs add provider usage coverage. These are curated anchors, not proof that a planned assertion measures the right property; independent review of actual outputs remains mandatory before qualification.

Scripted plumbing (no model):

```sh
PYTHONPATH=src:. .venv/bin/python -m evals.test_planning.evaluate --evidence .runs/test-planning-fixture-001
```

A local-provider run adds `--provider-config PATH` (an explicit `LocalModelConfig` JSON). Defaults: two repeats, concurrency one, five requests, four successful tool calls, 48000 total tokens, one output correction, 240-second task deadline, no task or SDK retry. Existing evidence directories are refused before dispatch. Every attempt keeps a native-message receipt with read paths, corrections, unknown tools, usage, response ids and failures. Missing usage is not zero, unanswered requests stay uncertain and are not retried, and private receipts are never committed. Freeze source, corpus and config before the first provider run; a false negative needs review and a new corpus baseline, never a rewritten run.

## Native unit observation set

`make eval AGENT=planning SET=unit` runs the frozen `unit` set (`python/unit/`): the same SQL construction concern over safe and unsafe source, using a recording dependency and no effect recorder. The reviewed plan calls the real function and limits its claim to query construction. This development set is not held out and does not replace the unchanged legacy comparison. Scripted results establish contracts and curated anchors, not live semantic accuracy.

## Versioned unit-first policy evaluation

`make eval AGENT=planning SET=unit-first` runs the frozen `unit-first` set (`python/unit-first/`, manifest `sets/unit-first.json`) under evaluator identity `planning-v2`. Its six inputs are identical to the legacy development set. Three traversal cases now expect native properties instead of an effect witness; the former `unsupported_observation` case is separately named `native_dependency_observation` and now admits a request-dispatch dependency double while excluding network-engine claims. Missing baseline and missing implementation cases still expect abstention. Original development files/results remain unchanged; witness-only legacy scores must not be presented as unit-first semantic regressions.

`SET=unit-v2` (`python/unit-v2/`) retains the two SQL unit inputs and updates the evaluator-only input criterion to explicit reviewed alternative breakout/tautology patterns. Those patterns require the quote breakout and matching operands for this fixture, reject ordinary account text containing OR or unequal operands, and admit the observed alternate `alice' OR '1'='1` (the application supplies the final closing quote). The shared evaluator has no language/CWE branch: patterns and property anchors belong to case metadata, never agent inputs. These are conservative curated anchors, not a general semantic proof or acceptance of arbitrary generated payloads. `SET=unit` preserves the v1 literal criterion and its frozen manifest for historical comparison. New reports record evaluator version; older reports are not rescored in place.

## Breadth set

`make eval AGENT=planning SET=breadth` (`--cases breadth`) runs the cases under `<language>/breadth/<case-id>/` (`input.json`, evaluator-only `oracle.json`, `case.json` metadata), frozen by `sets/breadth.json`; `dataset_sha256` is `evals.cases.set_digest` of that manifest. It is a development set, not held out; `RETIRED` is unchanged.

Forty cases, ten each for Java (Maven, JUnit 5 on JDK 17 and one JUnit 4 on JDK 8), JavaScript (Jest 24 on Node 8.17), Ruby (Minitest on 3.1) and Perl (Test::More/TAP via prove on 5.26). Every environment lists no witness facility, so ready reference plans use the SPEC-0078 native unit contract: a typed `observation` per test, no `witness`, and `observation_kind` in the oracle. Each language covers:

| Kind | Cases per language |
| --- | --- |
| `positive` (ready) | rejected traversal (`exception`), HTML/escaping (`return_value`), command construction through an injected recording double (`dependency_call`), archive extraction into a per-test directory (`fixture_state`) |
| `guarded` (ready) | guarded source; the plan must still exercise the guard (Java XXE, Jest prototype pollution, rack-protection path normalisation, Perl response splitting) |
| `injection` (ready) | instructions inside the saved baseline test; `forbidden_markers` check they are not obeyed |
| `abstention` (unsupported) | no executed baseline test; implementation absent from the inventory; a property the environment cannot observe (timing, ReDoS CPU time, TLS handshake, check-then-open race) |
| `transfer` (ready) | the Python `sql_dependency` recording-database shape in the framework's idiom |

Imported material: non-held-out `benchmarks/corpus/infosec-harness` variants (Java xxe/cmdi/sqli, JavaScript prototypepollution/cmdi/arginjection, Perl responsesplitting/xss/cmdi/sqli), sinatra rack-protection `path_traversal.rb` v2.0.1 (MIT) and an excerpt of vercel/ms 0.7.0 (MIT); the rest is synthetic. `case.json` records each source. Perl plans name `not_ok` as the security failure type because the TAP runner reports no exception type for a failed assertion. `tests/configuration/test_breadth_planning.py` checks the counts and that blanket approval, blanket refusal, a wrong symbol or observation kind, adversarial input in the control and obeyed injected text each fail the curated checks. Scripted results establish contracts and anchors only, not live planning quality.
