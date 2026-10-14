# Environment host evaluation

`make eval AGENT=environment [REPEAT=2] [PROVIDER_CONFIG=/absolute/config.json]`
uses the production agent factory and tools. All SandboxExecution calls receive synthetic,
exact-command observations. No command, repository code, shell, container or cluster runs.
Unrecorded commands receive a synthetic exit 126 refusal, recorded separately in the
attempt receipt as `unrecorded_commands`; this is not an observed operator-policy denial.
Even equivalent command spellings are unrecorded unless they match exactly. Live scores
therefore measure adherence to curated argv, not general setup judgement. Unknown delivery halts the production tool ledger.
Command and setup-correction budgets remain operator owned. Attempt receipts now record `setup_corrections` separately from output-schema corrections and preserve an unresolved correction run ID. The eight frozen cases do not exercise the new invocation corrections; production FunctionModel trajectories in tests/agents/test_environment.py cover their admission/refusal, and live recovery frequency and side effects remain unmeasured. Eight frozen development cases (`python/development/`, `java/development/`, `sets/development.json`) cover Python,
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

## Breadth set

`make eval AGENT=environment SET=breadth` (`--cases breadth`) runs 50 synthetic cases in the per-case layout
(`<language>/breadth/<id>/{input,oracle,case}.json`, manifest `sets/breadth.json`, identity `evals.cases.set_digest`): Python 4,
Java 12, JavaScript 12, Ruby 11 and Perl 11, which with the development set gives at least ten per language. Each
oracle is the development `FrozenCase` model without `name`; the replay, checks and receipts are unchanged. Toolchain
ids and runtimes follow `deploy/runtime-matrix.yaml` (image digests are placeholders) and every framework the
finalizer admits appears: pytest on CPython 3.12 and 3.7, junit5/junit4 on Temurin 17/8, jest on Node 8.17.0,
minitest on Ruby 3.1.7 and tap-harness on Perl 5.26.3.

Per language the cases cover a ready project test, registry and TLS failures, a build failure, a discovery failure
(pytest collection error, JUnit engine discovery error, Jest config validation error), a failing baseline test
(blocked; the layer is not checked because the skill names no layer for it), a skipped/xfailed first baseline
candidate followed by a passing one, an unsupported runtime with wording anchors (JDK 21, Node 18, Ruby 2.5,
Perl 5.36), prompt injection in a README, POM comment or CI file, unknown delivery, command-budget exhaustion and
the operator smoke-test baseline with an uncapped checkout listing. Ruby and Perl have no discovery-failure case:
their discovery is a file listing (`ruby -e Dir.glob`, `prove --dry`) with no realistic failure separate from the
build. The Java discovery command keeps the development set's `mvn -o test -DlistTests=true` convention, which
prints `Class#method` ids; it is a synthetic stand-in, not a captured Maven listing.

The observations are hand-written in the shape of `tests/agents/framework_outputs` and real tool messages, not
captured runs, so the set measures trajectory and contract adherence across languages, not setup judgement or
admission on real repositories. `tests/configuration/test_breadth_environment.py` checks counts and that wrong
status, wrong layer, versionless unsupported wording and a skipped first candidate fail the checks.
