# Staged multilingual baseline v1

This new operator-owned suite preserves existing frozen sets. Four minimal paired synthetic command-construction fixtures cover JavaScript node:test, Ruby Minitest, Perl Test::More and Java JUnit 5. Reuse the four Python pytest property fixtures in `probe_specialists/cases-v1.json` for SQLite query behavior, filesystem containment, returned fields and denied state mutation. `cases.revision_inputs` matches the pilot fixture projection and removes the paired revision, provenance and qualification label; specialist projectors subsequently remove peer inputs and identities. No model calls, container operations or native execution occur here.

The multilingual cases test a single generic property: production code must construct a literal argv request with shell interpretation disabled. A recording dependency captures arguments and supplies a return sentinel without implementing the guard. This does not measure actual shell parsing or execution. Both benign control and adversarial safety probes are required. Synthetic source was written in this repository; no new third-party code was imported.

`development_corpus_inputs()` reuses one already imported development case per Python/JavaScript/Java/Perl language for identification; it never selects held-out cases. Upstream provenance/licensing limits remain in `benchmarks/corpus/infosec-harness/SOURCE.md`; external Vul4J records remain metadata and cannot be counted as captured or native-qualified cases. Existing Ruby Rack source/test fixtures are under `benchmarks/cases/rack-static/`; broad Rails or RSpec qualification is not implied.

Native environment baseline is deliberately `None` in new fixtures. Planning must abstain until actual discovery and baseline execution establish evidence. Authors may draft source-only fixture probes; a draft is not executed support. Node and Perl executables were found on this host; Ruby and javac were not. Presence of java does not establish JUnit or Maven availability. No tools were installed.

Jest conventions already have an isolated composition cohort (`make eval AGENT=chain SET=jest`), but its Docker execution is separate from plain-host stage baselines. Native node:test and RSpec test selection/outcome adapters are not admitted by existing identity grammars; node:test here is a source-only convention fixture. Add RSpec only with an explicit native identity/outcome contract, rather than disguise it as Minitest. A language label never extends runtime support.

Run the existing agents in execution order: environment, identification, planning, control author, exploit author, immutable source-only validity review, native two-probe execution, evidence assessment and deterministic disposition. The ordinary host entry is `make eval AGENT=<environment|identification|planning|authoring|assessment> SET=<set> PROVIDER_CONFIG=<path>`. Environment/identification offer development; planning offers development/heldout3/unit/unit-v2/unit-first; authoring offers development/unit; assessment offers development/held_out/unit/unit-transfer. Split roles and validity review need their own preserved report/baseline rather than being counted as the legacy joint author.

`negative-cases-v1.json` records five required review/assessment strata. Each has frozen JS source and exactly two probe files as an outcome-blind `review_input`; evaluator labels stay outside that projection: copied target, mocked target, irrelevant assertion, fixture denial and missing seam. These are native node:test convention examples; no reviewer model has scored them and no execution outcome is claimed. The existing `probe_validation/fixtures/{copied,vacuous}` provide concrete Python starting points. Freeze source-only review before native outcomes; denial and missing seam stay inconclusive. Record unavailable stage datasets or native ports as coverage gaps, never as zero failures.

The new manifest binds synthetic source and negative source/patch examples. None of these additions promotes a baseline, claims semantic qualification or rewrites historical comparisons.

## Usable stage projections

`PYTHONPATH=src:. <repository-runtime-python> -m evals.experiments.staged_baseline.cases --stage planning` exports five typed `TestPlanningInput` plus `PlanOracle` cases: Python pytest, JavaScript Jest, Ruby Minitest, Perl Test::More and Java JUnit 5. `planning_cases()` returns those objects directly. These operator fixtures inject an admitted baseline identity to measure positive planning reasoning on the host; they do not claim the native test was executed. Baseline source is preserved read-only and fresh control/exploit paths are authorized separately. Node:test remains excluded from this positive set.

`--stage environment` exports the eight existing environment cases with deterministic command/observation ports (Python and Java positives plus registry/TLS/build/unknown-delivery/budget/unsupported failures). `--stage identification` projects four development-only existing corpus cases. `--stage validity` reuses three existing multilingual `ValidityInput` cases: valid JS recording dependency, copied JS target, Ruby alias with benign exploit input. They retain frozen expected labels separately; no native outcomes enter validity inputs. `validity_cases()` returns validated typed inputs. The new negative node:test examples are additional source-only review strata and are not a substitute for these admitted typed inputs.

All stage artifact copies are new versions under this directory; the original frozen sets are unchanged. Planning YAML is in the native Pydantic Evals file format and can be consumed by a staged driver without modifying the legacy suite registry. CLI export only serializes inputs and operator metadata; a live driver must separate them before model calls.

## Corrected identification target oracle v2

The v1 identification transfer score required the whole property citation, including JavaScript exports, Perl package/trailer lines and Java class/interface scaffolding. Preserve its original 2/8 range result and all eight outputs. `identification-oracles-v2.json` instead records operator-selected actual target lines: JavaScript 1, Ruby 1–3, Perl 3 and Java 4, for both revisions. Its separate manifest pins unchanged `cases-v1.json`; no language parser infers the oracle.

Run the sibling with a fresh evidence directory:

```shell
PYTHONPATH=src:. <repository-runtime-python> -m evals.experiments.staged_baseline.identification_v2 --evidence <fresh-directory> --provider-config <providers.json>
```

Omit the provider configuration for scripted wiring. This delegates to the same production identification factory and shared native host harness through additive explicit corpus/dataset-identity parameters. Default identification evaluations and the running staged-v1 module remain unchanged. A saved report can also be reassessed using `--reassess-report <original-report.json> --reassessment-output <new-file.json>`; that output is labeled corrected-oracle reassessment, makes no new model request or native execution, and preserves original assertions/output digests. Reassessment is distinct from a fresh live baseline and cannot erase the original measurement.

## Current final unit disposition

`assessment-unit-disposition-v2.json` captures four exact final `AssessmentInput` objects from the production `run_chain` typed ports. Scripted callbacks delegate the same production factories, prompts, dependencies and effective budgets as direct execution. Native runs execute only the exact operator-reviewed split references: eight revision runs, sixteen probe outcomes, all cleanup confirmed. Oracles stay in separate metadata. Source-only `ValidityInput` is never mixed into this final corpus.

```shell
PYTHONPATH=src:. <repository-runtime-python> -m evals.experiments.staged_baseline.unit_disposition --version v2 --evidence <fresh-directory> --provider-config <providers.json> --repeat 1
```

The final-only budget is 600 seconds, matching the current composition ceiling; the historical assessment evaluator retains its 1200-second default. The shared native harness accepts an explicit frozen corpus and restricted dataset identity while preserving legacy defaults. The unit evaluator checks native pair identities/outcomes, immutable source/plan-bound review, gate correctness, successful evidence reads and native receipt grounding. It does not reuse the historical witness-only grounding oracle. Unknown native ports/outcomes and scripted semantic-review calibration remain unqualified.

The initial v1 capture is preserved under its separate manifest and is explicitly historical (`--version v1`). Its existing scripted fixture reviewer incorrectly cited the first patch item for both calls. Actual native outcomes and typed review binding were retained, but the exploit call-site citation pointed at control code. V2 corrects only the fixture reviewer: each actual native identity selects its own frozen test body; its actual import/call, literal input, property assertion and corresponding source definition are cited. This Python AST use prepares/reviews a known operator fixture; it is not a new production policy/parser or language/CWE recorder requirement. Exact v1 and v2 capture-source snapshots are retained locally under `.runs/split-transition-baseline/`.

Initial v1 final-plumbing scoring failed the new receipt-grounding check because the fixture model preferred optional witness citations; a separate corrected scripted model cites actual native receipts and reads frozen reviews. Both failed and corrected reports remain local. V2 scripted final scoring passed four cases. These are fixture wiring results; independent live assessment and production validity calibration require separate evidence.
