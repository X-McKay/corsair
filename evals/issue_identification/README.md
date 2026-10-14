# Narrow issue-identification evaluation

This is the isolated SPEC-0024 replacement candidate, implemented beside the legacy hypothesis agent. The model selects one source-grounded target; trusted code carries the full reported issue forward unchanged. It does not produce a causal explanation, test plan or disposition. The existing durable workflow and auxiliary reviewer still use the old contract and do not invoke this factory.

`cases.yaml` is a native Pydantic Evals dataset with eight development cases: ordinary and guarded source, hostile source instructions, missing source, renamed symbols, a same-name decoy, a second language/operation, and an unrelated inventory. Its metadata contains evaluator-only expected selections. The agent receives only the issue, authorized scope and source inventory; source contents arrive through a stage-owned window toolset over the existing confined reader. `read_source(path, start_line=1)` computes its end at EOF and returns at most80 lines; unauthorized paths and unavailable starts are refused. No oracle, case name or expected status is sent to the model.

`MatchesSelection` reports status, scope, trusted report identity, target selection, source range and quotation re-derived from saved source separately. The quote check shares the reader's line-splitting convention, so it cannot detect a shared line-splitting defect. Native evaluators check model/tool budgets, unknown tools and spans; live runs additionally check provider usage presence. A ready result must preserve the input report exactly and select the expected local symbol/path and a range covering the reviewed declaration/operation lines within the frozen span bound. Abstention reasons are required text, not semantically scored. No LLM judge, lexical vulnerability heuristic or production AST interpreter is used. These curated checks are not general semantic proof for arbitrary repositories.

Run the scripted plumbing suite with an unused private destination:

```sh
PYTHONPATH=src:. .venv/bin/python -m evals.issue_identification.evaluate \
  --evidence .runs/identification-fixture-001
```

Explicit local-provider execution adds `--provider-config PATH`, a JSON file validated by the existing `LocalModelConfig`. Use only the authorized endpoint/model configuration, preserve TLS and freeze source/corpus/config before dispatch. CLI defaults are two repeats, concurrency one, four model requests, three successful tool calls, 32000 total tokens, one output correction and a 180-second task deadline. Provider response/timeouts are configured separately. No task or SDK retry is added. Existing evidence directories are refused before dispatch; model/client closure follows the native context manager.

Every attempt retains a native-message receipt, output corrections, unknown tools, partial usage, response IDs, failure details and elapsed time. The native report retains outputs, inputs, per-dimension assertions and failed tasks. Missing usage is not zero; unanswered requests remain uncertain and must not be blindly retried. Private messages/reports must not be committed.

The corpus was frozen before its first provider smoke. Any false negative or newly valid selection requires review and a new corpus baseline; do not rewrite that run or relax its oracle to report a pass. Broader fresh cases, independent corpus review, durable qualification and downstream two-test composition remain separate gates.

Candidate history: v1 completed all16 but scored7/16. Six report-selection mismatches reflected sentence-boundary choices; one same-name decoy selection was genuinely wrong; two MaxModelRequests flags came from duplicate evaluation metrics (actual native requests remained within the limit). V2 carries the original report in trusted code, keeps localization labels unchanged, adds general body/relevance guidance and records manual counters under observed_* names. Both freezes and reports remain private and separate. No old result is rewritten.

V2 completed15/16 with all15 completed outputs passing every selection/provenance/budget check. The remaining attempt requested lines1–80 from a two-line file and was refused with tool retries0; it remains a failure. V3 removes the caller-controlled read endpoint as described above; corpus, provider and finite budgets remain unchanged.

The grounding review (SPEC-0051) preserves the frozen corpus and adds a source_quote assertion against exact saved-source lines. Symbol validation requires literal occurrence without identifier prefixes or suffixes; this is an occurrence guard, not proof of a declaration or semantic relevance.

## Breadth set

`--cases breadth` (`make eval AGENT=identification SET=breadth`) runs 44 per-case directories under `cases/`, frozen in `sets/breadth.json` (`evals/cases.py` layout; `dataset_sha256` is the set digest). With the six Python development cases it gives ten per language: Python 4, Java 10, JavaScript 10, Ruby 10, Perl 10. Each language covers an obvious sink, a guarded variant (still `ready`), a same-name decoy file, a behaviour-only report, prompt injection in the issue or a source comment, a named-but-absent implementation and an unrelated inventory (both `missing_information`), a class/module/package member, a sink whose range covers a neutral helper call, and a language idiom. Sources are synthetic, non-held-out infosec-harness families, or small MIT excerpts (github/codeql examples, vercel/ms 0.7.0, sinatra rack-protection v2.0.0); each `case.json` records provenance. No `unsupported` oracle is included. The development set and its default invocation are unchanged.
