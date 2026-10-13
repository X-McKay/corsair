# Source of this copy

Everything in this directory except this file is a verbatim copy of `eval-corpus/` from
https://github.com/X-McKay/infosec-harness at commit `52aa2ac64f3d81139b609f18890ac52950d02933`
(2026-10-06), imported on 2026-10-13 under SPEC-0067. Both repositories belong to the same owner.
`external/vul4j_excerpt.NOTICE` and the `source` fields of `external/vul4j.json` carry the
Vul4J dataset attribution (CC-BY-4.0); Vul4J's GPL-3.0 code is not included.

Tree digest (`python -m evals.corpus.cases --tree-digest`, every file but this one):
`0d21afaa5ef667a4237935fe3475ffc0966d8194941a99bd5a7b07fcf5b8ebed`

Do not edit these files in place. A corpus change is made upstream and copied again with a new
commit and digest here. `README.md` and `manifest.json` hold the answer key, and `verification/`
holds tests that assert each variant's behaviour: all three are evaluator-only and never enter an
agent input or a sandbox (`evals/corpus/cases.py` is the only reader).
