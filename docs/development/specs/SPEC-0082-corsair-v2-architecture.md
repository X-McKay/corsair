---
id: SPEC-0082
kind: spec
title: Corsair v2 architecture
status: accepted
updated: 2026-10-14
related: [PLAN-0097]
---

# Corsair v2 architecture

This record is the numbered form of the redesign proposal Al reviewed on 2026-10-14 (Claude Doc "Corsair redesign: design, spec and architecture", https://claude.ai/code/artifact/7901a435-2b5b-4c99-95d5-984d4fa42bb8, sections 1 to 14). The repository mirror is [docs/design/corsair-v2-proposal.md](../../design/corsair-v2-proposal.md), regenerated from the doc whenever it changes. Where the proposal and this record differ, this record and its amendments win. [PLAN-0097](../plans/PLAN-0097-corsair-v2-build.md) is the build plan.

## Goal and scope

Corsair v2 validates one reported security issue against an exact revision, and against a fix revision when one exists, with exactly two native tests. It should work across languages, frameworks and CWEs without branching on any of them. It should be simpler than v1 and easy to evaluate agent by agent.

v2 keeps v1's contract:

- Two native tests per investigated revision: a benign control and a proof-of-vulnerability (PoV) test, both through the real application seam. The PoV test passes when it demonstrates the reported condition (Al, 2026-10-14).
- One frozen patch, run on both revisions.
- An outcome-blind validity review before execution.
- The five labels: LIKELY_EXPLOITABLE, LIKELY_NOT_EXPLOITABLE, INCONCLUSIVE, UNABLE_TO_RUN and ERROR.
- Coverage, finding, fix and evidence validity are reported separately.

v2 removes most of the machinery around that contract: per-framework report parsers, assertion readers, the witness, the model-proposed disposition, and duplicated composition paths.

Out of scope, as in v1:

- Discovering new vulnerabilities.
- Writing fixes.
- Editing or closing tickets, including writing back to ADO.
- Deployment-scope validation.
- Multi-request exploit chains.

A unit-level probe shows the reported condition at a seam. It does not show reachability from outside.

The order of error costs is fixed first, because every gate follows from it:

1. A false LIKELY_NOT_EXPLOITABLE is the costliest error.
2. The inconclusive rate comes second.
3. Cost and latency come last.

## Boundaries and design

### Stages and contracts

Each stage is a function of three things: its typed input, its config digest and the content hashes of its inputs. That is what makes replay and per-stage evals possible.

| # | Stage | Owner | Output |
| --- | --- | --- | --- |
| 1 | Intake | Code | Case: issue snapshot, repository, revision, optional fixed revision, scope |
| 2 | Ground | Grounding agent (placeholder) | GroundingBrief or none; advisory, read by no later stage |
| 3 | Select | Code | Runtime: one matrix row (image digest, framework, run template, exit-code map) |
| 4 | Investigate | Investigator agent | ProbePlan: target, seam, inputs, control brief, exploit brief, component to build, cited source |
| 5 | Build | Builder agent, then trusted replay | Recipe: setup argv, baseline test id, replay result; cached |
| 6 | Probe | Control Prober and Exploit Prober | ProbeDraft each: file path, test name, source |
| 7 | Review | Reviewer agent | Validity per probe per revision, without outcomes |
| 8 | Execute | Code | ProbeRun per probe per revision |
| 9 | Decide | Code | Verdict: label, rule id, terminal reason, report |

Every contract is a versioned Pydantic model in `src/corsair/v2/contracts.py`. Large content (source, logs, patches) travels as `ArtifactRef(uri, sha256, size)` and never inline in Temporal history. A schema change bumps the contract version, and replay only compares runs of the same version.

Investigate runs before Build (A1). The Investigator plans on read-only source with search and declares the component it needs. The Builder prepares only that component. Code checks the plan against the measured environment, and one budgeted replan is allowed.

### Agents

Each agent is self-contained under `src/corsair/v2/agents/<name>/`, holding `agent.yaml` (a native `AgentSpec`), `agent.py`, `tools.py`, `skills/`, `evals/` (its cases and promoted baseline) and a placeholder `release-policy.yaml`. The release policy stays empty and nothing enforces it until the gates resume. This is the package shape the v1 manifest and Harness specs (SPEC-0080, SPEC-0081) adopted; those records remain on main. Guidance lives in native Harness Skills.

| Agent | Job | Tools | Done when |
| --- | --- | --- | --- |
| Grounding (placeholder) | Report what human reviewers concluded about similar prior issues | Read-only graph tools over the retrieved context | The brief passes the trusted citation check, or no brief |
| Investigator | Locate target and seam, form the conditional hypothesis, write the two briefs, declare the component | Read-only `read_file`, `list_files`, `search` | The ProbePlan validates and every citation resolves in the snapshot |
| Builder | Find a setup that installs the project's own dependencies for the component and runs one existing native test | Shell in the build workspace (approved registries only), `read_file`, `list_files` | Trusted replay of its recipe in a fresh container passes the baseline test |
| Control Prober | Write the benign control test from the control brief | `read_file`, `write_test_file` (own path only) | Its draft is frozen |
| Exploit Prober | Write the proof-of-vulnerability test from the exploit brief: it asserts that the reported condition occurs | `read_file`, `write_test_file` (own path only) | Its draft is frozen |
| Reviewer | Judge, without outcomes, whether each test calls the real target, exercises its condition, asserts a relevant property and keeps doubles to dependencies | Read-only access to the frozen inputs | Validity emitted per probe, with citations |

The two probers are separate packages with separate evals and baselines. They share the probe-protocol skill, the framework skills, the test-file write tool and the draft contract. Each has its own AgentSpec, instructions, output check, budget and provider key. Neither ever sees the other's brief, draft or result.

Authors cannot run tests (D3). After both drafts are frozen, trusted code makes one mechanical check run of each on the vulnerable revision. This run is not investigation execution. It keeps only a mechanical class and discards the outcome:

| Classifier outcome | Mechanical class | Next action |
| --- | --- | --- |
| passed, assertion_failed, anomalous | ok | Nothing is returned to the author; continue to review |
| not_run, errored | not_run or errored | No runtime output is returned. The author gets the mechanical class, a fixed hint chosen from the exit class and the markers (not discovered, harness error, body did not start, raised before the check marker), and the full output of the row's syntax check if that check failed. The author corrects its draft (A2), and each correction is checked again, up to three corrections per author per draft version (`chain.MAX_MECHANICAL_FIXES`), stopping at the first `ok`; then frozen again |
| infra | infra | The attempt stops with `infra_error` (R1, ERROR) |

`anomalous` maps to `ok` because returning it would hint at the outcome. Application code can run before the test body, from a fixture, a setup hook, a module import or a class initializer. Any line of runtime output, even one that names the author's own file, can therefore carry an observation of the target. So runtime output is never returned.

The only text returned is mechanical by construction. Each matrix row may declare a syntax-check template that parses or compiles the probe file without running application code, for example `python -m py_compile {file}`, `node --check {file}`, `ruby -c {file}` or the row's test-compile step. Trusted code runs it before the check run, and its output is returned in full, capped at 4 KiB. A row whose check can execute code, such as `perl -c` running BEGIN blocks, must not declare one, and the authors on that row get only the fixed hints. Nobody sees the discarded outcome: not the authors, not the Reviewer, not the rule table. The Reviewer then reviews the frozen bytes, with a bounded feedback loop below. Execute runs only bytes that carry a bound review, and any change after review needs a fresh review before Execute.

#### Review feedback loop

When the Reviewer judges a probe invalid, that probe's author gets the review back and may revise, for a limited number of rounds (Al, 2026-10-14). Execute never runs inside the loop, so the loop stays outcome-blind.

1. **Rounds.** A review round reviews the whole frozen pair. There are at most three rounds (Al: three reviews in total): the first review and up to two re-reviews. After a round where either probe is invalid, each author whose probe is invalid gets one revision, so each author has at most two review revisions. These are separate from the one mechanical revision above. Every round and revision spends the one total budget (A2), and exhausting it ends the loop.
2. **Feedback.** An author receives only its own probe's review: the names of the failed checks (`calls_real_target`, `exercises_condition`, `assertion_relevant`, `doubles_only_dependencies`), the Reviewer's defect text (at most four defects of 1 KiB each) and the Reviewer's citations, kept only if they resolve to the author's own test file or to source the author may already read. It never receives a run result or mechanical outcome beyond the fixed hints above, the other probe's brief, draft or review, Grounding output, or any oracle. The Reviewer is outcome-blind, so its feedback carries no observation of the target.
3. **Re-binding.** A revision is a new `ProbeDraft` whose `revision_of` is the digest of the draft it replaces. The unrevised probe keeps its bytes. Trusted code freezes a new `FrozenPatch` with a new digest, runs the mechanical check on each changed draft, and asks for a fresh review of the whole new pair. Every `Validity` binds to the new digest, so a review of an earlier pair never counts.
4. **End.** The loop ends when both probes are valid, which goes to Execute on the reviewed digest, or when three rounds have run or the budget is exhausted with either probe still invalid. Then nothing executes and R2 gives INCONCLUSIVE (`test_invalid`), as before. An author whose probe was already valid is never asked to revise. If a fresh round rejects that probe, its author gets a revision only while rounds remain.
5. **Recording.** Each round and each revision is its own stage step (`review.<n>`, `probe.<role>.r<n>`) with its input, output, usage and bound digest. The verdict records the number of rounds and each author's revision count. For evals, every probe-author call is one attempt: a prober's `clean_attempt_rate` counts only drafts accepted at the first review, and a separate `accepted_within_limit` rate and mean revision count measure the loop. Each Reviewer call is one Reviewer eval case.

Example: the first live run's Reviewer rejected an exploit probe that patched `subprocess` globally instead of where the target module imports it (`doubles_only_dependencies` false, citing the patch line). Under this loop the Exploit Prober gets that defect and citation, patches at the import site, and the new pair is reviewed again.

A missing CWE skill never causes a refusal. The run is tagged `uncovered_cwe` for eval slicing.

### Grounding and ADO intake (placeholder)

This follows Al's placeholder description of the InfoSec Harness ADO intake and grounding agent, attached on 2026-10-14. Only the contracts, ports and fixture stubs are built now. ADO and graph connectivity is not built.

Intake:

- Intake gains a second source, Azure DevOps work items, behind the same intake port as GitHub issues.
- A work item becomes a Case in three steps: an operator field map (deployment data, not code), then the scanner header parser, then graph backfill of a missing file, line or CWE. Backfill never overwrites a value the work item supplied.
- A work item that establishes no repository is skipped and listed, never guessed.
- Only a `Commit:`-style field of 7 to 64 hex characters pins a revision.
- A person is never recorded as the source tool.
- The WIQL shape check and the item cap are enforced even against fixtures.

Grounding:

- Trusted code assembles a GroundingContext and never raises. The context holds the issue, its comments, decided neighbours by CWE and by similarity, and `degraded`, which names every retrieval that failed.
- The agent writes a GroundingBrief: a summary, precedents with verbatim quotes, an optional prior disposition, and caveats.
- A trusted citation check drops any precedent whose issue id is not in the retrieved set, or whose normalised quote is shorter than 12 characters or absent from the retrieved text. Each drop is recorded as a caveat.
- With an empty context, no brief is produced. With no graph configured, the stage records `degraded: not_configured` and the chain continues.
- The brief is advisory. It goes into the report for a person. No later stage reads it and the rule table never uses it. A prior human disposition of the same issue is in effect a label, so passing it downstream would leak a label into the evidence (D10).
- The chain never branches on the tracker. ADO is one adapter of the work-item source.

### Probe protocol and outcome table (D2, D8)

For each run, trusted code sets four environment variables: `CORSAIR_MARKER_START`, `CORSAIR_MARKER_CHECK` and `CORSAIR_MARKER_END` (paths inside the container) and `CORSAIR_TOKEN` (a fresh random string).

- Each test writes the start marker as the first statement of its body and the end marker as the last, after its assertions.
- Immediately before its checked assertion, each test writes the check marker: `holds` when the property it is about to assert is true, `violated` when it is not. For the control the property is the benign behaviour; for the PoV test it is the reported condition.
- Each test puts the token in the failure message of the assertion that follows its check marker. For the PoV test that is the assertion that the reported condition occurred; for the control test it is the benign-behaviour assertion. The role, not the token, says which probe failed.
- Each probe runs alone, using the matrix row's run-one-test template filled with only the planned file and test name.
- The container runtime gives the exit code, signal or timeout. The row's exit-code map sorts the code into `pass`, `test_failed`, `no_tests`, `harness_error` or `unknown`.

Rows are evaluated top to bottom, and the first match wins. Infrastructure exits come first. A harness error is split by the start marker: without it the test body never started, which is what a collection, import or compile failure of the probe file looks like (pytest exits 2 for these), so it is the author's `not_run` rather than the platform's `infra`; with it the harness failed around a body that ran, so it stays `infra`. A timeout, signal or missing exit code is `infra` whatever the markers say.

| Exit class | start | check | end | token | Outcome |
| --- | --- | --- | --- | --- | --- |
| timeout, signal, no exit code | any | any | any | any | infra |
| harness_error | yes | any | any | any | infra |
| harness_error | no | any | any | any | not_run |
| no_tests, or no start marker | any | any | any | any | not_run |
| pass | yes | holds | yes | no | passed |
| test_failed | yes | violated | no | yes | assertion_failed |
| test_failed | yes | absent | no | any | errored |
| any other combination | | | | | anomalous |

Only `passed` and `assertion_failed` are decisive.

#### PoV polarity (Al, 2026-10-14)

The exploit probe is a proof-of-vulnerability test in the sense of the DARPA Cyber Grand Challenge and Vul4J: it passes on the vulnerable revision and fails on the fixed one. A pass is positive proof that the reported condition occurs through the real seam. The classifier above does not change, because `passed` and `assertion_failed` already mean "the asserted property held" and "it did not". Only the rule table reads the PoV the other way round from the earlier security-regression form.

A passing test is easier to make vacuous than a failing one: an assertion that is always true passes, and in this form it would read as LIKELY_EXPLOITABLE. Three checks carry that risk:

- The Reviewer's `assertion_relevant` check also requires that the PoV assertion could fail on code without the reported condition. An assertion that holds whatever the target does is invalid (R2).
- The check marker is written immediately before the asserting statement and the end marker only after it, so a test that passes without reaching the assertion reads as `anomalous`, not `passed`.
- When a fixed revision is run, a PoV that also passes there gives INCONCLUSIVE (`not_differential`), not LIKELY_EXPLOITABLE. Only a decisive pass changes the label; an infrastructure or provider failure on the fixed revision still only makes the fix `not_verified`.

A token in the output alone cannot attribute a failure, because the whole test process can read the token. The check marker is what does: an unrelated exception raised before the assertion leaves no check marker and reads as `errored`, even if repository code printed the token. Forging all three signals takes deliberate code in the test or the repository. The outcome-blind review reads the test, and the comparison across revisions covers the repository. That residual is recorded as a limitation, not hidden.

Each framework skill ships a canary pair: one test that passes and one whose token assertion fails. A matrix row is admitted only when its canaries classify as `passed` and `assertion_failed` through its run template and exit-code map.

A framework whose exit code cannot separate a failed test from a harness error gets a small native-result reader for that one row. Nothing else in the table changes.

### Verdict rules (D4)

The label is a pure function of recorded facts. Rules are evaluated top to bottom, the first match wins, and its id is stored.

| Rule | Condition | Label |
| --- | --- | --- |
| R0 | Stopped before a model stage (no matrix row, build failed) | UNABLE_TO_RUN |
| R1 | Provider or infrastructure failure on the vulnerable revision: before any ProbeRun exists, or any vulnerable-revision probe whose outcome is `infra` | ERROR |
| R2 | Review missing or negative for either probe on the vulnerable revision | INCONCLUSIVE (test_invalid) |
| R3 | Vulnerable control not passed | INCONCLUSIVE (`control_failed` when the control's outcome is assertion_failed, otherwise the reason its outcome maps to) |
| R4 | Vulnerable PoV passed, and the PoV did not also pass on the fixed revision | LIKELY_EXPLOITABLE |
| R5 | Vulnerable PoV assertion_failed (the condition was not demonstrated), with its calibration listed | LIKELY_NOT_EXPLOITABLE |
| R6 | Anything else | INCONCLUSIVE (`not_differential` when the PoV passed on both revisions, else as below) |

Fix verification is a separate rule over the same facts. `verified` requires all of the following:

- R4 on the vulnerable revision.
- On the fixed revision, the control passed and the PoV is assertion_failed.
- A positive review for the fixed revision.
- The same frozen patch on both revisions.

Otherwise the result is `not_verified`, or `not_applicable` when there is no fixed revision. A provider or infrastructure failure on the fixed revision gives `not_verified`, with its terminal reason recorded in the fix result. It never changes the label decided from the vulnerable revision.

Calibration (a detector self-test or an ablation run) is recorded as calibration and never as proof of absence. `refuted_in_scope` stays disabled.

The terminal reason comes from a closed enum: `ok`, `no_runtime`, `build_failed`, `plan_unresolved`, `unsupported_scope`, `probe_not_run`, `probe_errored`, `probe_anomalous`, `test_invalid`, `control_failed`, `no_valid_observation`, `not_differential`, `budget_exhausted`, `provider_error`, `infra_error`, `cleanup_unconfirmed`. R3 and R6 take their terminal reason from the vulnerable-revision probes. R3 looks only at the control, R6 at both, checking `not_run` first, then `errored`, then `anomalous`:

- `probe_not_run` when either probe was `not_run`.
- `probe_errored` when either probe was `errored`.
- `probe_anomalous` when either probe was `anomalous`.
- `no_valid_observation` otherwise.

The fix result carries a terminal reason from the same mapping over the fixed-revision probes. A model may write a rationale once the label is fixed. It cannot change the label.

### Corrections, caches, modes and fact origins

- **A2, corrections under one total budget.** A schema error goes back to the same role. A review defect goes back to that author alone, for up to two review revisions, each with a fresh review of the re-frozen pair (Review feedback loop). A setup failure gets one more Builder episode. A seam that cannot exercise the condition gets one replan. An unknown dispatch stops the attempt. Per-stage limits never reset the total.
- **A3, three cache levels.** A recipe suggestion from similar manifests is revalidated before use. An exact environment artifact (exact source, recipe, image and dependency closure) can be reused. Execution evidence is never relabelled as a fresh run.
- **A4, explicit scope mode.** Repository-native and minimal-component modes are recorded as a scope choice. v1's pytest route disables project config, which can strip what a finding depends on.
- **A5, origin labels.** Each fact carries an origin label (`platform_observed`, `native_test_reported`, `model_reviewed` or `declared`).
- **A7, invalidation.** A prompt change needs a new plan and everything downstream. New test bytes need a new review and execution. A decision-rule change recomputes over saved evidence without model calls.

### Where language knowledge lives

| Place | Holds |
| --- | --- |
| Matrix row (`deploy/v2/runtime-matrix.yaml`) | Image digest, versions, evidence level, detection hints, approved build registries, run-one-test template, exit-code map, optional syntax-check template |
| Framework skill | How to name and place one test, read an environment variable, write a file, put a message on an assertion; the canary pair |
| CWE family skill (optional) | Benign and adversarial input shapes, the property to assert, which doubles keep production logic |
| Eval cases | Language-specific inputs and oracles, read by evaluators only |

Trusted code handles only image digests, argv lists, exit codes, file existence and substring search.

### Durability and workspaces (Approach 2)

- Trusted workers run the workflow and the agents. Each case gets a throwaway workspace, and the worker never runs inside a sandbox.
- One Temporal workflow runs per case, with no child workflow per stage. Native `TemporalDurability` turns each model request and tool call into an activity. Direct mode runs the same stage functions without a worker.
- There are three task queues: `model` (one slot), `workspace` and `control`.
- Each operation has a retry class. Model calls and reads get up to three attempts. Shell commands and probe runs execute exactly once, and an uncertain outcome is recorded as `infra`.
- Each run is pinned to its release tuple: worker image, lockfile, agent spec and skill digests, matrix digest and image digest.
- Docker and OpenShell implement PydanticAI's Workspace interface. Each episode follows acquire, verify, stage, run, collect, release.
- Containers have deterministic names and ownership labels recorded before creation. They run non-root, with no network except during Build, and with resource limits.
- A lost workspace fails that stage attempt and is rebuilt from the cached recipe.
- A scheduled sweep by label removes containers whose workflow has closed. Cleanup that cannot be confirmed is reported as `cleanup_unconfirmed`.
- Not adopted: signals, updates, approvals, continue-as-new, payload encryption, credential brokering, the policy prover, and a worker inside the sandbox.

### Runs, evals and benchmarks: one layout

Committed data:

| Path | Holds |
| --- | --- |
| `evals/e2e/<language>/<set>/<case-id>/` | Chain cases in three files: `input.json` (agent-visible), `oracle.json` (evaluator-only), `case.json` (pins, source, licence). Corpus pairs, benchmark cases and fixtures all live here, as sets named `corpus`, `benchmark` and `fixtures` |
| `src/corsair/v2/agents/<name>/evals/<language>/<set>/<case-id>/` | Per-agent cases in the same three files; `common` holds language-free cases |
| `src/corsair/v2/agents/<name>/evals/baselines/<set>.json` | That agent's promoted baseline, with metrics keyed by language and eval type |

Run output, ignored by git:

| Path | Holds |
| --- | --- |
| `.runs/chain/<run-id>/` | `run.json`, `stages/<nn>-<stage>/`, `workspace/<episode>/commands.jsonl`, `artifacts/<sha256>` |
| `.runs/evals/<agent>/<set>/<stamp>-<mode>/` | `summary.json`, `comparison.md`, one stage-shaped folder per case |
| `.runs/campaigns/<id>/` | Run ids and the campaign report |

Every stage folder holds `input.json`, `output.json`, `transcript.jsonl` and `usage.json`, so a recorded chain stage can be replayed as that agent's eval without conversion. `usage.json` has one shape everywhere: model requests, input and output tokens, tool calls, wall time, retries, and failures by layer. A missing value is null, never zero. Each root has an `index.jsonl`, and `corsair report` reads any of them. The command is `make eval AGENT= SET= [LANG=] [MODE=]`.

There are four eval types:

- **scripted:** no model.
- **replay:** a live model on recorded inputs.
- **live:** a live model with a real Docker workspace, for the Builder and both probers (D5).
- **e2e:** the whole chain.

A baseline holds, for each language and eval type:

- accuracy for each evaluator dimension;
- p50 and p95 latency;
- tokens and requests per case;
- terminal-reason counts.

### Standing rules

- The chain never branches on language, framework, CWE, tracker, issue, corpus id, repository or fixture.
- Oracles and held-out family names stay out of every agent-visible input. Held-out sets are never tuned on.
- Inference goes only to llm.almckay.io.
- Docker is the execution route. No credential, model endpoint or Temporal identity enters a container.
- Images hold only a language runtime and pinned test frameworks. A case project's versions never change.

## Acceptance and validation

Gates are deferred (Al, 2026-10-14 08:09Z). No kind or OpenShell gate, witness, held-out scoring or row upgrade to `live` runs until both of these hold:

1. At least three end-to-end runs reach the correct decisive label on both revisions, in at least three languages.
2. Every agent has a promoted baseline tracking accuracy, latency and tokens, split by language and eval type.

Canary pairs and failure-injection fixtures still run as ordinary development tests where they are cheap. Until something runs end to end, develop's PR path runs one offline job, `make test-v2`, with no model (Al, 08:28Z). The v1 suites, the image gate and the qualification and record guards stay runnable by hand and return with the gates and release policies.

Acceptance for the build:

- Every reference probe pair classifies to its oracle outcome on both revisions in Python, Java, Perl, Node and Ruby.
- Every matrix row's canaries classify correctly.
- Each agent has a frozen eval set and a scripted suite, plus a replay or live suite and a promoted baseline, with metrics by language and eval type.
- The Grounding stubs satisfy the invariants in its placeholder description:
  - A finding with no repository is skipped and listed.
  - The work-item id is set only by ADO intake.
  - Only a commit field pins a revision.
  - A short or absent quote drops its precedent.
  - "Degraded and empty" reads differently from "empty".
- The chain metrics are reported against the v1 baseline taken from main: false LIKELY_NOT_EXPLOITABLE rate, false LIKELY_EXPLOITABLE rate, pair flip rate, decisive rate, terminal-reason histogram, build success and cost. Reproduction sensitivity counts abstentions in its denominator (A6).

A schema-shaped `TestModel` output is wiring evidence only. Nothing in this record has been run.

## Decisions and open questions

The proposal's decisions and their status:

| # | Decision | Status |
| --- | --- | --- |
| D1 | Six agent packages: Grounding (placeholder), Investigator, Builder, Control Prober, Exploit Prober, Reviewer | Al, 08:09Z (revised from four) |
| D2 | Marker, token and exit code; no report parsers, assertion readers or witness | Accepted with the build kickoff |
| D3 | Authors get no test-running tool; trusted code runs frozen drafts once and returns only mechanical diagnostics | Al, 07:49Z |
| D4 | Deterministic rule table decides the label | Accepted with the build kickoff |
| D5 | Live evals for the Builder and both probers may use local Docker | Accepted with the build kickoff |
| D6 | Build on `develop` in `src/corsair/v2`; main stays untouched until Al replaces it | Al, 08:09Z |
| D7 | Reuse the verdict rule table, terminal reasons, per-stage replay and blinded runs from Al's InfoSec Harness v2 spec | Accepted with the build kickoff; Al also asked for the Grounding agent from that harness |
| D8 | Deterministic outcome table with an exit-code map per framework and a canary pair per row | Al, 07:49Z |
| D9 | Exactly two tests; native parametrisation inside a test is allowed | Accepted with the build kickoff |
| D12 | The exploit probe is a proof-of-vulnerability test that passes when it demonstrates the reported condition (PoV polarity) | Decided by Al, 2026-10-14 09:17Z |
| D13 | Reviewer feedback loop: three reviews in total, at most two review revisions per author | Decided by Al, 2026-10-14 09:09Z |
| D14 | Scope is provability, not category: a finding is in scope when both probes can prove it inside the workspace, deterministically and with no outbound network, using local stand-ins (a local server, a temporary file, an in-process double). The Investigator returns `unsupported_scope`, with the missing piece named, only when proof needs something the workspace cannot supply (a real remote endpoint, the host trust store, a system-wide policy, a specific library build). No vulnerability-category list exists anywhere | Decided by Al, 2026-10-14 09:33Z; implemented in #154 |
| D15 | Counterfactual assertion: the brief states `safe_observation`, what the test would see on a correct implementation, and the PoV assertion must be false there. Payload text echoed back in output, an argument list or a log is never proof | Implemented in #155 |
| D16 | Proof shows structure or effect: input merely reaching a dependency is never proof, because correct code usually passes input on as data rather than rejecting it. The PoV must show the input crossing from data into structure or into an effect it should not have | Implemented in #156 |
| D17 | The Reviewer stays outcome-blind: it judges whether each test is a valid experiment, never whether the code looks vulnerable. It must not call a PoV vacuous because the target looks safe, reject a control for not exercising the vulnerability, or steer an author toward what this code does | Implemented in #157 |

"Accepted with the build kickoff" means Al started the build on this proposal without objecting to that decision. Any of them can be reopened.

Defaults in force until Al decides otherwise:

- **D10:** may the Investigator read Grounding precedents with their dispositions removed? Default: no, until Grounding has a baseline.
- **D11:** does the first build PR remove v1's source, tests and eval runners from develop? Default: yes; v1 runs from main to supply its baseline.
- **Calibration for R5:** whether R5 should require calibration at all is still open. Default: R5 lists its calibration and does not require it.
- **Grounding unknowns:** the grounding agent's second and third structural guarantees and its tool signatures are not legible in the source description. The placeholder stubs only what is legible.
