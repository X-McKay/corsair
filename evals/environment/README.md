# Environment host evaluation

`make eval AGENT=environment [REPEAT=2] [PROVIDER_CONFIG=/absolute/config.json]`
uses the production agent factory and tools. All SandboxExecution calls receive synthetic,
exact-command observations. No command, repository code, shell, container or cluster runs.
Unrecorded commands receive a synthetic exit 126 refusal, recorded separately in the
attempt receipt as `unrecorded_commands`; this is not an observed operator-policy denial.
Even equivalent command spellings are unrecorded unless they match exactly. Live scores
therefore measure adherence to curated argv, not general setup judgement. Unknown delivery halts the production tool ledger.
Command and setup-correction budgets remain operator owned. Attempt receipts now record `setup_corrections` separately from output-schema corrections and preserve an unresolved correction run ID. The eight frozen cases do not exercise the new invocation corrections; production FunctionModel trajectories in tests/agents/test_environment.py cover their admission/refusal, and live recovery frequency and side effects remain unmeasured. Eight frozen development cases cover Python,
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


Versioned correction: `development-v2` uses `cases-v2.json` and `manifest-v2.json`.
Select it explicitly with `python -m evals.environment.evaluate --cases development-v2`
(or the environment suite's `SET=development-v2`). The original `development` set,
`cases.json`, manifest and historical receipts remain unchanged. V2 declares the
recorded locked pip, build, collection, baseline-test and offline Maven command
arguments in the agent-visible repository source. It preserves the eight case
statuses, failure layers and command budgets; unknown delivery still requires the
first dispatched receipt, and the budget case still requires the admitted prefix.
The exact-command double and oracle remain unchanged: no alternative spelling is
silently accepted, and an early unrelated refusal does not satisfy the trajectory.

Prompt v9 adds a generic runtime precheck before setup and concise halt feedback:
no follow-up setup commands after a halt, no invented run ID for a refused call,
and blocked output after an observed failure. Native correction admission remains
unchanged. Comparing original v1/live with v2/current changes both fixture source
and procedure; it cannot isolate a prompt effect. The corrected scripted 8/8 result
checks fixture/contracts, not provider capability or runtime readiness. A fresh
explicit v2 provider run at unchanged caps is needed for that narrower comparison.
