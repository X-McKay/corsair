# Paired corpus cases

[SPEC-0067](../../docs/development/specs/SPEC-0067-eval-corpus-import.md) turns the infosec-harness corpus copied under [`benchmarks/corpus/infosec-harness/`](../../benchmarks/corpus/infosec-harness/SOURCE.md) into Corsair cases. Offline only: nothing here runs a case or reaches the chain.

`cases.load()` returns one `CorpusCase` per topic directory: 40 pairs and 2 unpaired topics across Python, Java, JavaScript, Perl and C. The variant whose upstream truth is `potentially_exploitable` is the baseline revision and the other variant the candidate, so the hypothesised chain oracle is completed / reproduced / verified; an unpaired topic has only a baseline and is expected at completed / not_reproduced / not_applicable. `agent_input()` gives identification the shared finding text and the baseline variant's files under a neutral case id. Variant directories, verdicts, the manifest, the corpus README and the verification tests stay evaluator-only, and the loader refuses verdict words in anything an agent can read (the upstream hygiene rule, ported).

Splits are fixed by a salted digest: per language, the quarter of cases with the lowest digest is held out. Held-out ids appear only in `held_out.json` (case id to the SHA-256 of its finding, oracle and both trees), are counted but never named in the runtime report, and must not be cited under `docs/development/`. `python -m evals.corpus.cases --freeze-held-out` is the only way to rewrite the manifest.

```sh
PYTHONPATH=src:. .venv/bin/python -m evals.corpus.cases --tree-digest   # must match SOURCE.md
```

`external/vul4j.json` (58 Vul4J pairs at remote commits, nine of them already in the benchmark inventory) is copied as data only. Those cases need SPEC-0037 acquisition and proof-test masking before any use; they are not loaded as cases.

`python -m evals.corpus.campaign prepare --directory .runs/corpus/pilot --case <development-id> --provider-config <private.json> --images <images.json>` freezes a finite development campaign. Each pair produces a positive baseline/candidate request and an independent candidate-only negative request, with neutral source repository names. `--repeat` declares repeats before dispatch. Preparation selects the split before reading source trees; it does not rewrite the frozen held-out manifest.

`python -m evals.corpus.campaign run --directory .runs/corpus/pilot --provider-config <private.json> --images <images.json> --slots 1` invokes the existing full product runner serially with unchanged stage defaults. Source, provider settings, images, profiles and timeout must match preparation. Every slot has a record before dispatch. A native exclusive file lock refuses overlapping dispatchers. Started slots reconcile only against a final native record and matching frozen request; unresolved delivery remains unknown and is never automatically rerun. Uncertain delivery or cleanup blocks later dispatch until reconciled. Failed slots are retained. Deliberate reruns use a fresh campaign directory. `report --directory <directory>` regenerates JSON/Markdown denominator and stage summaries without dispatching. The timeout is per native command, with the existing stage deadlines; it is not a whole-investigation deadline.

Expectations remain upstream hypotheses pending independent oracle review. Exact matches compare an admitted final assessment with the three-part expectation, never a gate ceiling. Reports preserve unknown, unstarted and failed slots; missing telemetry remains unknown. Plain Docker results remain unqualified. This entry does not add a scheduler or run generated code on the host.
