# Environment host evaluation

`make eval AGENT=environment [REPEAT=2] [PROVIDER_CONFIG=/absolute/config.json]`
uses the production agent factory and tools. All SandboxExecution calls receive synthetic,
exact-command observations. No command, repository code, shell, container or cluster runs.
Unrecorded commands receive a synthetic exit 126 refusal, recorded separately in the
attempt receipt as `unrecorded_commands`; this is not an observed operator-policy denial.
Even equivalent command spellings are unrecorded unless they match exactly. Live scores
therefore measure adherence to curated argv, not general setup judgement. Unknown delivery halts the production tool ledger.
The command budget remains operator owned. Eight frozen development cases cover Python,
Java/Maven, registry/TLS/build failure, unsupported runtime, unknown delivery with attempted
follow-up, and budget exhaustion. README injection is untrusted source.

Native Pydantic Evals reports and attempt receipts preserve usage, messages, command records,
output digests, failures, observed command counts, corrections and latency. Scripted token
counts are estimates. Live provider mode uses explicit LocalModelConfig; absent or partial provider
token coverage excludes that attempt from token means and sample counts. Measured zero
counters remain observations; scripted token counts remain labeled estimates. The dataset manifest refuses changed bytes. There is no promoted
baseline before a person chooses a run; two same-set runs compare through evals/run.py.

These checks assess contracts, citations/reads, curated commands, status/layer, trajectory,
budgets and SDK instrumentation. Synthetic output cannot qualify setup, policy enforcement,
application test discovery/execution, dependency closure, sandbox replay or durability.
The cases are development fixtures adapted from existing contract tests, not captured benchmark
observations or a held-out semantic validation set. Fresh benchmark observations and independently
written held-out cases are required before prompt tuning or runtime admission.

Unsupported-runtime truth has bounded evaluator-only wording anchors for required and prepared
versions. An inverted claim fails even with correct source quotations. This is a curated semantic
regression, not validation of arbitrary natural-language requirements.
