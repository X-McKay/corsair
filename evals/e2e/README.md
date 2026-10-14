# End-to-end cases

Whole-chain cases in the [eval layout](../README.md): `evals/e2e/<language>/<set>/<case id>/`, manifests in `sets/`.

| Set | Language | Cases | Input | Run with |
| --- | --- | --- | --- | --- |
| `fixture` | python | 5 | `ChainInput`: which reviewed variant each purpose's workspace holds ([fixture_chain](../fixture_chain/README.md)) | `make eval AGENT=chain SET=fixture` |
| `jest` | javascript | 2 | `{"case": <benchmark case id>}`; manifest and expected result stay under `benchmarks/cases/` | `make eval AGENT=chain SET=jest` (live, Docker) |
| `corpus` | python | 17 | a `corsair-issue-request/v1` issue request; `repository.git` beside it holds both variants as root commits ([corpus/issues.py](../corpus/issues.py)) | `uv run corsair run --issue-json evals/e2e/python/corpus/<case>/input.json` |
| `corpus_negative` | python | 2 | a corpus case's issue text pointed at its own not-exploitable variant (`revision` = `fixed_revision`) | `uv run corsair run --issue-json evals/e2e/python/corpus_negative/<case>/input.json` |

`oracle.json` is evaluator-only: the chain's expected stop stage and gate (`fixture`), the benchmark manifest path (`jest`), the corpus expected file (`corpus`), or the expected label with its reason (`corpus_negative`). The corpus inputs are regenerated and compared by `tests/unit/test_corpus_issues.py`; `python -m evals.corpus.issues --root <dir> --set corpus` writes fresh copies elsewhere. Corpus families that are held out (`evals/corpus/held_out.json`) are never captured here.
