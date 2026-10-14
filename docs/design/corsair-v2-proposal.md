<!-- Mirror of the Claude Doc https://claude.ai/code/artifact/7901a435-2b5b-4c99-95d5-984d4fa42bb8, regenerated from it whenever the doc changes. Numbered records: SPEC-0082 and PLAN-0097 under docs/development. -->

# Corsair redesign: design, spec and architecture

Oct 14, 2026 · Al McKay

## 1. Decisions for Al

Seven choices shape this redesign. Each has a recommendation; the rest of the document assumes the recommended answer, and every other choice follows from these.

| # | Decision | Recommended | Alternatives |
| --- | --- | --- | --- |
| D1 | How many agents | **Four agent packages** (Builder, Investigator, Prober, Reviewer), with the Prober invoked twice in separate contexts for the control and security probes | One investigator agent with skills; or keep today's six roles and seven factories |
| D2 | How a probe outcome is read | **Reach marker + runtime failure token + exit code**, with one operator-owned run-one-test argv template per framework. Delete every report parser, assertion reader and witness recorder | Keep per-framework JUnit/Surefire/TAP/Jest/Minitest readers and the planned-failure-line match |
| D3 | Do probe authors execute their drafts | **Yes, with blinded feedback**: errors are shown in full, a completed run says only "completed" | Source-only drafting, as today |
| D4 | Who decides the label | **A deterministic rule table** over recorded facts; an optional model rationale writer cannot change the label | Today's assessment agent proposal capped by `admit()` |
| D5 | Agent evals for the two executing agents | **Builder and Prober live evals may use a local Docker workspace**; CI stays scripted on recorded workspaces | Keep the strict no-container rule for every agent eval |
| D6 | Where v2 is built | **Side by side in this repository** as a new package, sharing the #131 eval corpus; v1 is deleted when v2 matches it on the same frozen sets | New repository; or rewrite in place on main |
| D7 | Borrowing from the InfoSec Harness v2 spec | **Allow the four ideas named in section 10** (verdict rule table, terminal reasons, per-stage replay, blinded probe runs), which relaxes the earlier "interaction and kick-off only" rule | Keep the rule and drop those ideas |

One further question has no recommendation yet: how a LIKELY\_NOT\_EXPLOITABLE label shows that the security assertion could have failed, without adding a third test. Section 12 lists the options.

**Amended after the clean-slate spec:** D3 now recommends a trusted correction step instead of an author-run tool, and D8 and D9 are new. Section 13 has the details and supersedes earlier sections where they differ.

**Amended again for the build (Al, 08:09Z):** D1 is now six agents, with separate Control and Exploit Probers and a Grounding placeholder. Gates are deferred until end-to-end runs and per-agent baselines exist, and all work lands on a develop branch. Section 14 has the details and supersedes earlier sections where they differ.

**Decision status, 14 October.** The table below gives where each decision stands. The tables above keep the original recommendations for the record.

| # | Where it stands |
| --- | --- |
| D1 | Al revised it (08:09Z): six agents, namely Grounding (placeholder), Investigator, Builder, Control Prober, Exploit Prober and Reviewer |
| D2 | Accepted with the build kickoff: marker, token and exit code, now with a check marker (section 14) |
| D3 | Al agreed (07:49Z): authors get no test-running tool; one mechanical check run after freezing |
| D4 | Accepted with the build kickoff: the rule table decides the label |
| D5 | Accepted with the build kickoff: live Builder and prober evals may use Docker |
| D6 | Al revised it (08:09Z): build on develop in `src/corsair/v2`; main is untouched until Al replaces it |
| D7 | Accepted with the build kickoff; Al also asked for the Grounding agent from his InfoSec Harness |
| D8 | Al agreed (07:49Z): deterministic outcome table, exit-code map per framework, canary pair per row |
| D9 | Accepted with the build kickoff: exactly two tests, parametrisation inside a test allowed |
| D10 | Default in force: the Investigator does not read Grounding output |
| D11 | Default in force: v1 is removed from develop; v1 baselines come from main |

"Accepted with the build kickoff" means Al started the build on this proposal without objecting to that decision, and he can reopen any of them.

| # | Decision | Recommended | Alternatives |
| --- | --- | --- | --- |
| D8 | Outcome reading when a framework hides assertion messages | **Agreed by Al: a deterministic truth table over trusted-observed facts (exit code by framework exit-code map, start and end marker files, token), with a canary pair checked per matrix row** | Native-result adapters for every framework, as the clean-slate spec prefers |
| D9 | Test cardinality | **Exactly two tests, as today; native parametrisation inside a test is allowed** | Two logical groups of several tests each, as the clean-slate spec allows |

## 2. Summary

Corsair v2 keeps today's contract (two native tests, one frozen patch, both revisions, outcome-blind review, five headline labels) and removes most of the machinery around it. Four small agents gather evidence; a deterministic spine owns sandboxes, execution, the label and the report.

The main change is how a probe's outcome reaches trusted code. Today trusted code parses five native report formats and matches the security failure to a planned exception type, file, function and line (`core/disposition.py:258-268`). In v2 the trusted side gives each run a fresh token in an environment variable. The test writes a reach marker when its body starts and puts the token in the security assertion's failure message. Trusted code then reads three facts per run: did the marker appear, what was the exit code, and did the token appear in the output. Every language and framework can read an environment variable and write a file, so this needs no parser per framework.

Other changes:

- **Fewer agents.** Identification and planning merge into one Investigator. The two authors become one Prober package called twice with separate contexts and budgets. The assessment agent keeps only its outcome-blind validity review.
- **The verdict is a rule table.** Recorded facts map to a label, a rule id and a terminal reason. No model proposes a disposition.
- **The environment stage becomes a cached Builder.** One agent loop finds a setup recipe in a sandbox. Trusted code replays the recipe in a fresh container and requires one native baseline test to pass. The recipe is cached per repository, revision and image, so corpus pairs and repeated runs build once.
- **Authors can run their drafts.** Feedback is blinded, so an author can fix compile and collection errors without seeing whether the security assertion held.
- **One code path.** One Temporal workflow runs the chain. Agents run directly in evals because native `TemporalDurability` is transparent outside a workflow.
- **Model concurrency becomes a worker setting.** The local model serves one caller well. A Temporal task queue with one model slot serialises inference across runs, which replaces the cross-thread ordering by message.

The result is fewer places that know about a language. Today framework facts live in at least five places (the matrix, `HARNESSES`, environment `FRAMEWORKS`, `AGENT_FRAMEWORK` and `_ID_FILES`). In v2 they live in one matrix file and one guidance skill per framework.

## 3. Goals, non-goals and standing rules

The ranking of errors is fixed first, because every gate below follows from it. A false LIKELY\_NOT\_EXPLOITABLE is the costliest error. The inconclusive rate comes second, then cost and latency.

**Goals**

1. Validate one reported security issue against an exact revision, and against a fix revision when one exists, with two native tests.
2. Work across languages, frameworks and CWEs with no branch in code on any of them.
3. Make every label reproducible from stored facts without calling a model.
4. Let any stage be re-run on recorded inputs and scored on its own, so a prompt, skill, budget or model change is judged against that stage's baseline before it is composed.
5. Scale to the 66-configuration campaign and beyond, limited by inference capacity rather than by coordination between people or threads.
6. Keep the source small enough that one person can read all of the trusted code. The target is under 6,000 lines of `src`, against 17,948 today. That target is my estimate, not a measurement.

**Non-goals**, unchanged from today: discovering new vulnerabilities, writing fixes, editing or closing tickets, deployment-scope validation, and multi-request exploit chains. A unit-level probe shows the reported condition at a seam, not reachability from outside.

**Standing rules the design keeps**

- The chain never branches on language, framework, CWE, issue, corpus id, repository or fixture. Language knowledge lives only in matrix rows, framework guidance skills and run templates. Eval content may be language-specific.
- Exactly two finding-specific tests per investigated revision: a benign control and a security safety regression, both through the real application seam.
- Oracles and held-out family names stay out of every agent-visible input. Held-out sets are never tuned on.
- Inference goes only to llm.almckay.io.
- Docker is the day-to-day execution route. The kind/OpenShell gate runs once per milestone and is required for sandbox, policy and gateway changes.
- Images hold only a language runtime and pinned test frameworks. No unpinned packages, and never a change to a case project's versions.
- Missing telemetry is unknown, not zero. Failures stay attributable to a layer (admission, build, discovery, assertion, agent, provider, cleanup).

## 4. Architecture

Three zones, with the trust boundary between the first two: the trusted worker holds the workflow and the agents, the Docker workspace runs every repository command, and shared services hold the model queue, artifacts and the language data.

```text
Trusted worker (workflow + agents)            Docker workspace (per case)        Shared services
  Intake -> Ground -> Select -> Investigate     Build replay, probe runs,          model queue (1 slot),
  -> Build -> Probe (control, exploit)          canaries; argv in, exit codes,     artifact store,
  -> Review -> Execute -> Decide                markers and output back            runtime matrix + skills
```

The diagram in the Claude Doc shows the same three zones; the stage order above is the current one from section 14.

The chain runs left to right on the top row, then right to left on the second. The four tinted stages are agents; their model calls go through the one-slot model queue, and their outputs and the containers' outputs are stored as content-addressed artifacts. The worker sends the workspace only argv lists and files, and reads back exit codes, output and declared files. No credential, model endpoint or Temporal identity ever enters a container.

## 5. Spec

The chain has eight stages. Four are agents and four are trusted code. Each stage is a function of (typed input, config digest, input content hashes), which is what makes replay and per-stage evals possible.

### Stages and contracts

| # | Stage | Owner | Input | Output | Runs |
| --- | --- | --- | --- | --- | --- |
| 1 | Intake | Code | `--id` or `--issue-json` | `Case`: issue snapshot, repository, revision, optional fixed revision, scope | Per run |
| 2 | Select | Code | `Case`, repository manifests | `Runtime`: one matrix row (image digest, framework, run template) | Per run |
| 3 | Build | Builder agent, then code replay | `Case`, `Runtime` | `Recipe`: setup argv list, baseline test id, smoke result | Per (repo, revision, image); cached |
| 4 | Investigate | Investigator agent | `Case`, `Recipe`, read-only source | `ProbePlan`: target, seam, inputs, two probe briefs, cited source | Per run |
| 5 | Probe | Prober agent, twice | One probe brief each, workspace with the recipe applied | `ProbeDraft`: file path, test name, source | Per probe |
| 6 | Review | Reviewer agent | Frozen patch, plan, reported condition, source per revision. No outcomes | `Validity` per probe per revision | Per run |
| 7 | Execute | Code | Frozen patch, `Recipe`, `Runtime`, revisions | `ProbeRun` per probe per revision | Per run |
| 8 | Decide | Code (+ optional rationale model) | `Validity`, `ProbeRun`s | `Verdict`: label, rule id, terminal reason, report | Per run |

Every contract is a versioned Pydantic model. Large content (source, logs, patches) travels as an `ArtifactRef(uri, sha256, size)`, never inline in Temporal history. A schema change bumps the contract version, and replay only compares runs of the same version.

### The four agents

| Agent | Job | Tools | Done when | Replaces |
| --- | --- | --- | --- | --- |
| Builder | Find a setup that installs the project's own dependencies and runs one existing native test | `shell` in the build workspace (network to approved registries only), `read_file`, `list_files` | Trusted replay of its recipe in a fresh container passes the baseline test | Environment agent |
| Investigator | Locate the reported target and seam, form the conditional hypothesis, and write the two probe briefs | Read-only `read_file`, `list_files`, `search` | `ProbePlan` validates and every citation resolves in the snapshot | Identification + planning |
| Prober | Write one native test from one brief, at the planned path and name | `read_file`, `write_test_file` (own path only), `run_probe` (blinded) | Its draft completes under `run_probe`, or its budget ends | Control author + exploit author |
| Reviewer | Judge, without outcomes, whether each probe calls the real target, exercises its condition, asserts a relevant property and keeps doubles to dependencies | Read-only `read_evidence` over frozen inputs | `Validity` emitted with citations per probe | Assessment validity call |

Each agent is a native `AgentSpec` file plus a small Python module for tools and output validation, the shape #132 already adopted. Skills are native Harness Skills: one per framework (how to name a test, run it alone, read the token variable, write the marker), and optional ones per CWE family. A missing CWE skill is never a refusal; the run is tagged `uncovered_cwe` for eval slicing.

The control and security Probers never see each other's brief, draft or results. They are one package, so a prompt fix reaches both.

### The probe protocol

At execution time trusted code sets two environment variables for each run: `CORSAIR_MARKER` (a path inside the container) and `CORSAIR_TOKEN` (a fresh random string). Both probes write the marker as the first statement of the test body. The security probe uses the token as its assertion's failure message, for example `assert safe, os.environ['CORSAIR_TOKEN']` in Python or `assertTrue(safe, System.getenv("CORSAIR_TOKEN"))` in JUnit.

Trusted code runs each probe alone with the framework's run template from the matrix row, filled only with the planned file and test name. It then classifies the run:

| Marker | Exit code | Token in output | Outcome |
| --- | --- | --- | --- |
| absent | any | any | `not_run` |
| present | 0 | absent | `passed` |
| present | non-zero | present | `assertion_failed` |
| present | non-zero | absent | `errored` |
| present | 0 | present | `anomalous` |
| (timeout or container failure) |  |  | `timeout` / `infra` |

The token is new for every run, so it cannot be hard-coded, cached or found in repository text. A probe that prints it outside the assertion is visible to the Reviewer, and gives `anomalous` when the test passes. The control probe carries no token and must give `passed`.

`run_probe`, the Prober's iteration tool, runs the same classifier on the vulnerable revision. It returns full output for `not_run` and `errored`, since those are mechanics the author must fix. For `passed`, `assertion_failed` and `anomalous` it returns only `completed`. An author can therefore make its test compile and reach the seam, but cannot steer toward an outcome.

### Verdict rules

The label is a pure function of recorded facts. Rules are evaluated top to bottom; the first match wins and its id is stored.

| Rule | Condition | Finding | Label |
| --- | --- | --- | --- |
| R0 | Stopped before a model stage (no matrix row, build failed) | none | UNABLE\_TO\_RUN(reason) |
| R1 | Provider or infrastructure failure | none | ERROR(reason) |
| R2 | Review missing or negative for either probe on the vulnerable revision | inconclusive | INCONCLUSIVE(test\_invalid) |
| R3 | Vulnerable control not `passed` | inconclusive | INCONCLUSIVE(control\_failed) |
| R4 | Vulnerable security `assertion_failed` | reproduced | LIKELY\_EXPLOITABLE |
| R5 | Vulnerable security `passed`, and the negative evidence rule (section 12) holds | not\_reproduced | LIKELY\_NOT\_EXPLOITABLE |
| R6 | Anything else | inconclusive | INCONCLUSIVE(no\_valid\_observation) |

Fix verification is a separate rule on the same facts. `fix: verified` needs R4 on the vulnerable revision, `passed` control and `passed` security on the fixed revision, a positive review for the fixed revision, and the same frozen patch on both. Otherwise it is `not_verified`, or `not_applicable` with no fixed revision.

The report keeps today's separate fields (execution, finding, fix, evidence validity) and adds the rule id and a terminal reason from a closed enum: `ok`, `no_runtime`, `build_failed`, `plan_unresolved`, `probe_not_run`, `probe_errored`, `test_invalid`, `control_failed`, `budget_exhausted`, `provider_error`, `infra_error`, `cleanup_unconfirmed`. A model may write a rationale after the label is fixed; it reads the recorded facts and cannot change the label.

## 6. Generic across languages, frameworks and CWEs

Adding a framework in v2 means adding data and one guidance file, never code. Trusted code only ever handles an image digest, an argv list, an exit code, a file's existence and a substring search, and none of those depends on the language.

### Where language knowledge lives

| Place | Holds | Who reads it |
| --- | --- | --- |
| Matrix row (`deploy/runtime-matrix.yaml`) | Image digest, runtime and framework versions, evidence level (`image-only` or `live`), detection hints (manifest file names), registry hosts allowed at build time, the run-one-test argv template | Select and Execute stages |
| Framework skill (`skills/frameworks/<name>/SKILL.md`) | How to name a single test, where test files go, how to read an environment variable and write a file in that language, how to put a message on an assertion, common setup commands | Builder and Prober agents |
| CWE family skill (optional, `skills/cwe/<family>/SKILL.md`) | What a benign and an adversarial input look like, which property to assert, which dependency doubles keep the production logic | Investigator and Prober agents |
| Eval cases (`evals/<agent>/<language>/<set>/`) | Language-specific inputs and oracles | Evaluators only |

A run template is the one piece of framework knowledge trusted code applies. Today's operator-owned pytest argv in `investigation/frameworks.py` is already one. Examples, to be checked against each image before a row lands:

| Framework | Run-one-test template |
| --- | --- |
| pytest | `python -m pytest -c /dev/null --noconftest -p no:cacheprovider {file}::{name}` |
| JUnit 5 / Maven | `mvn -o -q -Dtest={class}#{name} -DfailIfNoTests=false test` |
| Test::More / prove | `prove -v {file}` (one test file per probe) |
| Jest | `node node_modules/jest/bin/jest.js --ci {file} -t {name}` |
| Minitest | `ruby -Itest {file} -n {name}` |

### What this removes

A survey of main for this proposal found at least eleven places where code branches on a language or framework name today, among them `nodes/runtime/detect.py:77`, `ports/test_runner.py:180-202`, `agents/environment/frameworks.py:221`, `composition/direct.py:438` and `agents/test_authoring/static.py:103`. All of them go. So do the five report parsers in `reports/` (686 lines), the five runner drivers in `adapters/`, the Python-only witness probe and the Python AST admission check. Detection becomes a manifest-name lookup driven by matrix rows.

### Why it generalises across CWEs

No contract names a vulnerability class. A probe brief names a target, a seam, a benign input, an adversarial input and a property to assert. Path traversal, command construction, SQL construction, XXE, deserialisation and SSRF-style checks all fit that shape, with a recording double at the dependency seam where the effect would leave the process. A CWE that needs behaviour beyond a seam (a real database engine, a real network) is planned as integration scope or refused as `unsupported_scope`, and that decision is the Investigator's, recorded and evaluated, not a code path.

## 7. Durability, sandboxing and scale

Agents and the workflow run on a trusted worker; every command from a repository runs in a disposable container. This is the vendor comparison's Approach 2, and it is already Corsair's topology, so the change here is mostly removal.

### Temporal

- **One workflow, `Investigation`, and no child workflow per stage.** Stages 1, 2, 7 and 8 are plain activities. Stages 3 to 6 call `agent.run()` inside the workflow, and native `TemporalDurability` turns each model request and tool call into an activity. Today's `run_direct` and the separate child workflows (`workflows/chain.py:96-136`) collapse into this one path.
- **Direct mode is the same code without a worker.** `TemporalDurability` is transparent outside a workflow, so evals and `corsair run --local` call the stage functions directly. Nothing is duplicated.
- **Three task queues, each with a slot limit:** `model` (one slot, so one inference request at a time across all runs), `workspace` (container slots sized to the Docker host) and `control` (workflow tasks, cheap). The model queue's limit replaces the rule that only one thread runs live inference, and makes the 66-configuration campaign a matter of submitting 66 workflows.
- **Retry classes per operation**, as the comparison document recommends: model requests up to three attempts with a finite deadline and provider retries off; reads up to three; a shell command or probe execution exactly once, with an uncertain outcome recorded as `infra` rather than retried; container create and remove bounded retries against the same labelled identity.
- **Bounded episodes.** One workflow investigates one case and ends. No sessions, no continue-as-new, no human approvals: nothing Corsair does writes outside its own artifacts.
- **Pinned worker versions.** A run records its release tuple (worker image, lockfile, agent spec and skill digests, matrix digest, image digest) and is pinned to the worker deployment that started it.

### Workspaces

The sandbox is a PydanticAI Workspace backend behind one port with two implementations:

| Backend | Used for | Qualified by |
| --- | --- | --- |
| Docker | Every day: Builder shell, `run_probe`, Execute, CI image checks | Image-only matrix evidence; the failure-injection tests below |
| OpenShell | Once per milestone, and before any sandbox, policy or gateway change merges | The existing kind/OpenShell gate, upgrading rows to `live` |

Each episode is acquire, verify, stage, run, collect, release. A container is created with a deterministic name and labels carrying the workflow and run ids, from a digest-pinned image, as a non-root user, with no network except during Build (approved registry hosts only) and with CPU, memory, PID and time limits. Collect copies only the declared outputs (marker, captured output, the patch) into the artifact store with checksums. A scheduled reconciler lists labelled containers, checks the exact workflow execution, and removes those whose owner has closed. Cleanup that cannot be confirmed is reported as `cleanup_unconfirmed`, never hidden.

The Builder's recipe is replayed by trusted code in a fresh container, so a probe never runs in the container an agent typed into. An optional gVisor runtime (`runsc`) for the Docker backend is a cheap hardening step to measure later; it is not required.

### Scale

The binding limit is inference: one locally hosted model at about 130 tokens per second. Three design choices respect it. The Builder recipe cache means a corpus pair or a rerun pays for setup once. The Reviewer and the rationale writer are small calls. Stages that need no model (Select, Execute, Decide) never wait on the model queue. Container slots scale with the Docker host, and a second Docker host joins by running another `workspace` worker.

## 8. Evaluation and the improvement loop

Every stage is scored alone on recorded inputs, and the whole chain is scored on frozen cases; a change ships only if no gated metric regresses beyond its noise band. Quality evidence and platform evidence stay separate gates, as the comparison document recommends.

### Recording and replay

Each run stores, by content address: every stage's input and output, config digest and release tuple, full agent transcripts and tool calls, workspace command logs, token counts and wall time, and the rule id and terminal reason. `corsair replay --stage prober --from <run-set> --config <digest>` re-runs one stage on recorded inputs with a changed prompt, skill, budget or model and scores it with that stage's evaluator. Downstream stages can be chained or skipped. Cached recipes mean replay does not rebuild.

### Per-agent evals

The #131 layout stays: `evals/<agent>/<language>/<set>/<case-id>/{input,oracle,case}.json` and `evals/e2e/<language>/<set>/<case-id>/`, run by `make eval AGENT= SET= [LANG=]`, with a promoted baseline per set and mode.

| Agent | Scripted (CI, no model) | Live (local model) | Primary metric |
| --- | --- | --- | --- |
| Builder | Recorded workspace: each command maps to its recorded output; an unrecorded command fails closed | Real Docker workspace (needs D5) | Replayed recipe passes the baseline test |
| Investigator | `FunctionModel` oracles over fixed source | Fixed source snapshot | Target and seam match the oracle; citations resolve |
| Prober | Recorded `run_probe` results | Real Docker workspace on the case's built image (needs D5) | Probe completes; marker reached; the reference revision gives the oracle outcome |
| Reviewer | `FunctionModel` oracles | Frozen labelled pairs, including copy, mock-the-target and vacuous-assertion traps | Agreement with labelled validity, false-valid rate first |

### Chain metrics

| Metric | Definition | Gate |
| --- | --- | --- |
| False LIKELY\_NOT\_EXPLOITABLE rate | Known-exploitable cases labelled not exploitable | Must not rise; target 0 on paired cases |
| False LIKELY\_EXPLOITABLE rate | Known-safe cases labelled exploitable | Must not rise |
| Pair flip rate | Pairs where both revisions get the right label | Must not fall |
| Decisive rate | Cases not INCONCLUSIVE, UNABLE\_TO\_RUN or ERROR | Reported; trend up |
| Terminal-reason histogram | Count per terminal reason, by language and CWE family | Reported; drives the next change |
| Build success | Cases reaching a replayed passing recipe, per language | Reported |
| Cost | Model requests, tokens, tool calls and wall time per case, p50 and p95 | Must stay within budget |

Noise bands come from three repeat runs of the baseline. Coverage, finding, fix and evidence validity are reported separately, as the campaign brief requires. Held-out sets are scored only at milestones and never read during tuning.

### The loop

1. Run the development sets and the latest campaign batch.
2. Group by terminal reason and stage; open the largest bucket.
3. Read 10 to 20 transcripts from it and write a one-line failure label for each.
4. Change one thing (prompt, skill, validator, budget, model) and replay only that stage.
5. If the stage metric improves, run the chain gate; keep the change only if no gated metric regresses.
6. Add the cases that motivated the change to a development set, never to a held-out set.

This is today's corpus improvement loop (`docs/runbooks/corpus-improvement-loop.md`) with replay making step 4 cheap. On the evidence so far, environment-stage reliability is the largest bucket, so the Builder and its cache come early in the migration.

### Platform gates

These run without a model, in CI where possible: worker loss after a recorded model result resumes without a new provider call; a container killed mid-command yields `infra`, not a retry; a container from another run is refused; a terminated workflow's containers are removed by the reconciler; a deleted container mid-run yields workspace-lost, not a fresh attach; artifact collection that fails means the run is not reported complete. A forged token in repository text, a probe that prints the token outside its assertion, and a probe that never writes the marker each have a fixture.

## 9. Comparison with current Corsair

Most of what Corsair decided over the last two weeks survives; what goes is the per-framework parsing, the duplicated composition paths and the model's role in the verdict. Figures for today come from main at 14715ea.

| Area | Today (main 14715ea) | v2 | Status |
| --- | --- | --- | --- |
| Test contract | Two native tests, control and security regression, one frozen patch, both revisions | Same | Kept |
| Validity review | Separate outcome-blind call before execution (#130) | Same, as its own Reviewer package | Kept |
| Author independence | Two packages, `control_authoring` and `exploit_authoring`, over shared `probe_authoring` | One Prober package, two invocations with separate briefs, contexts and budgets | Simplified |
| Author execution | Source-only drafts; `run_tests` exists only in the legacy `test_authoring` | Blinded `run_probe` | Changed (D3) |
| Identification and planning | Two agents | One Investigator | Merged; measured in the migration, split again if accuracy drops |
| Environment | One agent run per investigation, sandbox released after (`direct.py:328`) | Builder with trusted replay and a recipe cache | Changed |
| Outcome reading | Five report parsers (`reports/`, 686 lines), five runner drivers, id grammars, planned-failure match on type, path, function and line | Marker, token, exit code; one run template per framework | Replaced (D2) |
| Witness | Python audit-hook recorder, optional since #130 | Removed; linkage rests on review, revision difference and the optional ablation run (section 12) | Dropped |
| Disposition | Assessment agent proposes; `admit()` caps it | Rule table; optional label-locked rationale | Replaced (D4) |
| Composition | `run_chain` in `composition/direct.py`, plus one child workflow per stage in `workflows/chain.py` | One workflow; direct mode is the same functions | Simplified |
| Framework facts | Matrix, `HARNESSES` (only pytest and jest routed), environment `FRAMEWORKS`, `AGENT_FRAMEWORK`, `_ID_FILES` | Matrix row and framework skill | Consolidated |
| Agent definitions | Native `AgentSpec` files and Harness Skills (#132) | Same | Kept |
| Runtime matrix | Seven images with `image-only` and `live` evidence | Same rows, plus a run template and detection hints | Kept, extended |
| Labels and result fields | Five labels; execution, finding, fix | Same, plus rule id and terminal reason | Kept, extended |
| Eval layout | #131 layout, scripted and live modes, promoted baselines | Same, plus per-stage replay | Kept, extended |
| Entry point | `uv run corsair run --id` or `--issue-json` | Same | Kept |
| Inference | Named provider profiles; local model | Same; one model slot across runs | Kept |
| Legacy code | `test_authoring`, `issue_analysis` and their workflows still in `src` | Not carried over | Dropped |
| Size | 17,948 lines in `src`, 26,645 in `tests`, 9,421 in `evals`, 1,236 test functions | Target under 6,000 in `src` (estimate) | Reduced |
| Records | 295 numbered records, about 2.7 MB of Markdown under `docs/` | One design doc, a short decision log, and per-agent eval reports generated from runs | Proposed, optional |

The last row is a process change, not architecture. The records have kept work honest across many sessions, but at 2.7 MB they are now nearly three times the size of the Python source (0.97 MB), and several current reservations already collide with numbers on main. A smaller record set would make the redesign easier to keep current. I would treat it as a separate decision after D1 to D7.

## 10. What the attached documents recommend, adopted and rejected

The four vendor reference architectures (Claude, Manus, OAI, Gemini) and the two comparisons split on one question: does the Temporal worker run inside the sandbox, or outside it with commands delegated in? Corsair runs hostile repository code, so it follows the documents that keep the worker outside (OAI, Gemini, and the comparison's Approach 2). The InfoSec Harness v2 spec is a different kind of input, a triage design rather than a platform, and four of its ideas transfer directly.

### Adopted

| Recommendation | Source | Where in v2 |
| --- | --- | --- |
| Trusted worker runs agents; untrusted execution goes to a per-episode workspace through PydanticAI's native Workspace interface | OAI, Gemini, comparison | Section 7 |
| `TemporalDurability` on a normal `Agent`, never the deprecated `TemporalAgent`; stable agent names and toolset ids | All four | Section 7 |
| One explicit workflow and a static agent registry, not a queue or fleet per agent | OAI, comparison | Section 7 |
| Runtime profiles as separately versioned records | Manus | Already Corsair's matrix rows |
| Retry class per operation; an uncertain command outcome is surfaced, never blindly repeated | OAI, comparison | Section 7 |
| Acquire, verify, stage, run, collect, release, plus an independent reconciler; no claim that `finally` guarantees cleanup | OAI, comparison | Section 7 |
| Artifact references with checksums instead of blobs in history | All four | Section 5 |
| A failure-injection matrix as an implementation gate | OAI, comparison | Section 8, platform gates |
| Platform correctness and agent quality as two separate gates; schema-shaped `TestModel` output is wiring evidence only | Comparison, Claude | Section 8 |
| Native Skills for guidance; skill text is content, never authority | OAI, Claude | Section 6 |
| Deterministic verdict rules with a stored rule id; a label-locked rationale | InfoSec Harness v2 | Section 5 |
| Terminal reason on every result, and its histogram as the roadmap | InfoSec Harness v2 | Sections 5 and 8 |
| Per-stage replay on recorded inputs | InfoSec Harness v2 | Section 8 |
| Blinded probe runs, so an author fixes mechanics without steering the outcome | InfoSec Harness v2 | Section 5 |

### Rejected

| Recommendation | Source | Why not for Corsair |
| --- | --- | --- |
| Worker inside a long-lived OpenShell sandbox (Approach 1) | Claude, Manus | Corsair's core job is running untrusted builds and tests. Hostile code would share a domain with the worker's Temporal credentials and other runs' files |
| One sandbox, queue and fleet per agent | Claude | Four agents share one trust class; per-agent fleets add operations with no security gain |
| OpenShell provider profiles brokering model credentials | Claude, Manus | Inference is a local endpoint called from the trusted worker with no secret; the workspace never calls a model |
| Per-run OpenShell sandbox as the everyday route | OAI | Al chose Docker for day-to-day work; OpenShell stays the milestone gate |
| `openshell-prover` and OPA checks in every CI run | Claude, Manus, ADR export | They prove policy files, not Corsair's evidence. Keep them in the milestone gate for policy changes |
| L7 MCP allowlists, payload envelope encryption, human approval updates, signals and long sessions | Claude, Manus, Gemini | Corsair has no MCP tools, no multi-tenant history, no external writes and no conversations |
| Lazily creating the sandbox inside a tool call | Gemini | Leaks sandboxes when the activity times out mid-create; ownership must exist before creation |
| A custom `agent.yaml` platform manifest | Manus, Claude, ADR export | #132 already uses native `AgentSpec`; a second manifest language duplicates it |
| Static honesty checks on probe source (imports the target, no mocks of the sink) | InfoSec Harness v2 | They need a parser per language. v2 uses the outcome-blind review, the revision difference and the optional ablation run instead |
| Three probe-emitted markers (precondition, sink returned, oracle fired) | InfoSec Harness v2 | Asks every probe to instrument the target's internals. One reach marker plus the assertion token gives the trusted side what the rules need |
| Dollar budgets per agent | InfoSec Harness v2 | The local model costs nothing; budgets are requests, tokens and wall time |
| OWASP Benchmark and historical ticket decisions as eval sets | InfoSec Harness v2 | The OWASP Benchmark is already excluded from the corpus; Corsair has no ticket history to mine |
| Engineer-week estimates | Comparison | Not used for planning here; the migration is gated by evals instead |

The documents disagree on one detail that matters: Gemini says never to run a worker inside a transient sandbox, while Manus recommends long-lived sandboxed workers. Both are beside the point for Corsair, since its worker runs in neither.

## 11. Migration plan

Build v2 eval-first, beside v1, and switch only when v2 matches v1 on the same frozen sets. Each phase is one or two PRs and ends at a measured gate; no phase needs the kind cluster except the last.

1. **Scorer and baseline.** Write a standalone chain scorer that reads v1 result files and the #131 corpus, reports the chain metrics and terminal reasons, and promotes a v1 baseline on the development sets. No behaviour change. *Exit:* a v1 baseline with noise bands from three repeats.
2. **Trusted spine without a model.** Docker workspace backend, the probe protocol classifier, Execute, the rule table and the report, driven by hand-written reference probe pairs for the existing fixtures in Python, Java, Perl, Node and Ruby. *Exit:* every reference pair gives the oracle outcome on both revisions, and the platform-gate fixtures pass. This phase alone tests D2 across five languages.
3. **Prober and Reviewer.** Given recorded v1 plans, the Prober writes probes with blinded `run_probe`, and the Reviewer judges them. *Exit:* valid-pair rate at least v1's 7 of 8 on the probe-specialists set, and the Reviewer catches every copy, mock and vacuous-assertion trap in its set.
4. **Builder and cache.** *Exit:* replayed-recipe success above v1's environment baseline per language. This is the phase most likely to move the decisive rate.
5. **Investigator.** Merged identification and planning. *Exit:* target and seam accuracy no worse than v1's two agents together; if worse on large repositories, keep two agents.
6. **One workflow and the campaign.** Temporal workflow, three queues, reconciler, replay command. Run the 66-configuration development baseline. *Exit:* no gated chain metric below v1; false LIKELY\_NOT\_EXPLOITABLE no higher.
7. **Milestone gate and switch.** OpenShell workspace backend through the existing kind gate, held-out sets scored once, then v1 packages deleted in one PR.

Paused work maps onto this plan. Lane 2's tool defects and lane 4's Perl reader would not be carried over. The held failure-token simplification becomes phase 2. #131's corpus carries over unchanged, and #127's candidate-free rules carry over as rule-table conditions.

## 12. Risks, open questions and evidence

The biggest risk is that the probe protocol is untested: nothing in this document has run. Phase 2 of the migration exists to settle it cheaply, before any agent work.

### Open question: evidence for a negative

Rule R5 needs some sign that the security assertion could have failed. Today SPEC-0040 calibration covers part of this, and #130 weakened it for unit plans. Options considered (decided as D18, below):

1. **Review only.** The Reviewer affirms the security probe exercises the reported condition; the label carries `sensitivity: unverified`. Simplest, weakest.
2. **Revision difference when available.** A fixed or known-vulnerable sibling revision showing `assertion_failed` proves sensitivity. Strong, but most negatives have no such revision.
3. **Ablation run.** Trusted code reruns the security probe with the cited target file replaced by a stub that raises. If the outcome does not change, the probe never depended on the target, which catches the copied-target failure the campaign measured. It is language-neutral, but in compiled modules a broken file fails the whole build, so it proves less there.
4. **A third, positive-control test** against an unsafe dependency double. Strongest, but it breaks the two-test rule.

**Decided (D18, Al, 14 October 11:26Z): retry plus flag.** A failing PoV alone is weak proof, as the python-vuln false negative showed. Before any LIKELY\_NOT\_EXPLOITABLE, the chain runs one independent second exploit attempt: a new Exploit Prober call that never sees the first draft, its review or its outcome, with its own review loop and one vulnerable run, reusing the first attempt's control byte for byte. The new pair gets a fresh outcome-blind review in which only the Exploit Prober may revise; if the control is rejected or the pair stays invalid, the case is INCONCLUSIVE, never LIKELY\_NOT\_EXPLOITABLE. The negative path therefore runs three tests, so D9 becomes exactly two tests per attempt and at most two attempts per case, with each verdict decided on one attempt's pair. If the second PoV passes, reviewed and differential, the case is R4 (LIKELY\_EXPLOITABLE). R5 applies only when both attempts' PoVs are assertion\_failed after positive reviews; any other second-attempt outcome gives INCONCLUSIVE or ERROR as its own rule says. This costs one more author call on the negative path only. Every R5 also carries `sensitivity: unverified` until the labelled corpus measures LNE precision per language and vulnerability class; after that it carries lne\_precision instead (negative-verdict precision with its set, not reproduction sensitivity), which the merge-to-main gate reads. Options 2 and 3 stay recorded as calibration, never as proof of absence.

### Risks

| Risk | Effect | Mitigation |
| --- | --- | --- |
| A framework hides assertion messages in its default output | Token absent; failures read as `errored` | The run template adds the framework's verbose flag; the reference pairs in phase 2 check every framework |
| A probe catches the assertion error or marks itself expected-to-fail | Wrong exit code | Gives `anomalous` or `errored`, not a decisive outcome; the Reviewer sees the source |
| A probe writes the marker and token without calling the target | False LIKELY\_EXPLOITABLE on a single revision | Outcome-blind review, the ablation run, and the revision difference where a fix exists |
| Merging identification and planning loses accuracy on large repositories | More `plan_unresolved` | Phase 5 measures it; keep two agents if it drops |
| Blinded `run_probe` still leaks the outcome through timing or output size | Author steers the result | Fixed-shape reply for completed runs; no tails, no durations |
| A native Docker Workspace backend may not exist in Harness 0.55 | Corsair writes and maintains its own | The existing `adapters/docker_image.py` (173 lines) is the starting point; keep it behind the native interface |
| Inference capacity | One model slot makes the campaign slow | Measured, not hidden; the recipe cache and small Reviewer calls reduce demand |

### What was checked and what is inferred

**Checked against main at 14715ea:** the stage routing in `composition/direct.py:469-757`; the planned-failure match in `core/disposition.py:258-268`; `HARNESSES` routing only pytest and jest (`investigation/frameworks.py:48-73`); the per-stage child workflows (`workflows/chain.py:96-136`); the language branches listed in the generic section; agent construction through `Agent.from_spec` with Harness Skills; line counts (17,948 in `src`, 26,645 in `tests`, 9,421 in `evals`), 1,236 test functions and 295 numbered records; pinned versions (pydantic-ai-slim 2.55.0, Harness 0.55.0, temporalio 1.34.0, openshell 0.1.3). Valid-pair and baseline figures are quoted from `docs/development/CURRENT.md`, not rerun.

**Inferred, not tested:** that the marker and token protocol works on all five frameworks; the run templates as written; the 6,000-line target; that blinded feedback improves completion without leaking outcomes; that the recipe cache lifts the decisive rate; that one model slot is enough throughput; the ablation run's value. No model, Docker or cluster run was made for this proposal.

**From the attached documents, not verified here:** SDK behaviours they describe, such as `TemporalDurability` transparency outside a workflow and the Workspace backend interface. The attachments themselves say they were not integration-tested.

## 13. Amendments after the clean-slate spec

The clean-slate spec and this proposal agree on the core: four agent implementations, two author instances, an outcome-blind reviewer, a deterministic kernel with no post-execution model, delegated execution and one graph. It adds ten ideas worth adopting. It disagrees on three points, which are now D3, D8 and D9.

### Adopted

| # | Change | Replaces |
| --- | --- | --- |
| A1 | **Investigate before Build.** The Investigator plans on read-only source with search and declares what it needs (component, framework, fixtures). The Builder then prepares only that component, and code checks the plan against the measured environment, with one budgeted replan. This avoids building a whole monorepo for a one-library finding | Stage order in section 5, where Build came before Investigate |
| A2 | **Bounded corrections under one total budget.** A schema error goes back to the same role. A review defect goes back to that author alone, for one revision and a fresh review. A setup failure gets one more Builder episode. A seam that cannot exercise the condition gets one replan. An unknown dispatch stops the attempt. Per-stage limits never reset the total | Nothing; v2 had no correction rules |
| A3 | **Three cache levels:** a recipe suggestion (similar manifests, must be revalidated), an exact environment artifact (exact source, recipe, image and dependency closure), and execution evidence (never relabelled as a fresh run) | "Cached per repository, revision and image" in sections 2 and 7 |
| A4 | **Repository-native and minimal-component modes as an explicit, recorded scope choice.** Today's pytest route disables project config and conftest (`-c /dev/null --noconftest`, `investigation/frameworks.py:43`), which can strip the middleware a finding depends on | Implicit sanitised run templates in section 6 |
| A5 | **An origin label on each fact:** `platform_observed`, `native_test_reported`, `model_reviewed` or `declared`, so the report shows what a conclusion rests on | Nothing |
| A6 | **More metrics.** Track reproduction sensitivity with abstentions counted in the denominator, valid-experiment yield, fix-verification precision and correct abstention, next to false dismissals, because a zero false-dismissal rate means nothing if the system abstains often. With zero errors in n independent cases, the 95% upper error bound is 1 − 0.05^(1/n), about 3% at n = 100. Rank failure buckets by risk, not only by size | Chain metrics and loop step 2 in section 8 |
| A7 | **An invalidation table** saying what each change forces to rerun. A prompt change needs a new plan and everything downstream. New test bytes need a new review and execution. A decision-rule change only recomputes over saved evidence, with no model calls | Nothing |
| A8 | **Three named kinds of replay:** workflow replay (Temporal history), experiment reproduction (a frozen bundle, no model) and agent re-evaluation (a new stochastic run on recorded inputs) | The single `corsair replay` in section 8 |
| A9 | **A comparison record for the fixed revision** with invariants, intended changes, observed differences (dependencies, build outputs) and confounders. This lets a dependency-upgrade fix be judged on its real change set | The "same frozen patch" fix rule in section 5, which stays as one invariant |
| A10 | **Measure developer tasks, not line counts.** Track that a new CWE needs no workflow or kernel edit, that a prompt change is evaluable without redeploying, and that a frozen bundle reproduces without a model | The 6,000-line target in section 3 |

The spec also found two defects on main, both confirmed. Runtime libraries are declared only in the dev dependency group (`pyproject.toml:14-25`), so an installed package cannot resolve them. An issue that names no file is refused (`investigation/build.py:201`). v2 fixes both by construction: it declares runtime dependencies and gives the Investigator search.

### Disagreements

**D3, author execution.** The spec keeps authors source-only and lets trusted code return mechanical diagnostics only when they can be separated from the security outcome. That is the same blinding as `run_probe` with less tool surface. I now recommend its form: after freeze, trusted code runs both probes once on the baseline. A `not_run` or `errored` result returns that author's own diagnostics for one revision (A2). A completed run returns nothing.

**D8, outcome reading: agreed as a deterministic check (Al, 07:49Z).** Trusted code decides each probe's outcome from facts it observes itself, with no parser and no model. Every rule below is a fixed table.

1. **Exit status** comes from the container runtime: exit code, signal, or timeout.
2. **An exit-code map per framework**, stored as data in the matrix row, sorts the code into `pass`, `test_failed`, `no_tests`, `harness_error` or `unknown`. For pytest, 0 means pass, 1 test failed, 5 no tests, and 2, 3 and 4 harness error. Maven, Jest, prove and Minitest each get their own row, checked on the image.
3. **Two marker files**, written outside the output streams. The test writes `start` as the first statement of its body and `end` as the last, after its assertions. A passing test leaves both. A failed assertion leaves only `start`.
4. **The token** goes in the security assertion's failure message. It says that the failure came from that assertion, not from an earlier error.
5. **Each probe runs alone** with the run-one-test template, so the exit code belongs to that one test.

| Exit class | start | end | token | Outcome |
| --- | --- | --- | --- | --- |
| pass | yes | yes | no | `passed` |
| test\_failed | yes | no | yes | `assertion_failed` |
| test\_failed | yes | no | no | `errored` |
| no\_tests, or no `start` | any | any | any | `not_run` |
| harness\_error, timeout, signal | any | any | any | `infra` |
| any other combination (for example pass with no `end`, or a token on a pass) |  |  |  | `anomalous` |

Only `passed` and `assertion_failed` are decisive. The checks overlap, so a test that fakes one signal (exits 0 early, or prints the token) disagrees with another and lands in `anomalous` rather than a decisive outcome. Faking all of them together needs deliberate code, which the outcome-blind review reads. The comparison across revisions and the ablation run cover the rest.

**A canary pair per matrix row** checks the table itself. Each framework skill ships two tiny reference tests, one that passes and one whose token assertion fails. When a row lands, and again at each milestone gate, trusted code runs both through the row's run template and exit-code map, and the row is admitted only if they classify as `passed` and `assertion_failed`. This makes "the exit-code map and template are right for this image" a recorded fact, `image-only` or `live` like the rest of the row. Phase 2 of the migration runs the canaries on all seven images first.

A framework whose exit code cannot separate a failed test from a harness error (if one exists) gets a small native-result reader for that one row. Its exit class then comes from the report, and the rest of the table is unchanged.

**D9, test cardinality.** The spec allows control and security groups of several tests. Your standing rule is exactly two tests. I recommend keeping two and allowing native parametrisation inside a test.

**On negatives, the spec settles part of section 12's open question.** A detector self-test or an ablation run is calibration and is recorded as such, never as proof of absence. `refuted_in_scope` stays disabled, as today's kernel already does. R5 therefore yields `not_reproduced` (LIKELY\_NOT\_EXPLOITABLE) with its calibration listed. D18 settles the rest: R5 lists calibration without requiring it, and instead needs a second independent failed attempt and carries a sensitivity flag.

### Not adopted

The OWASP Benchmark as an eval source stays out, since the corpus already excludes it. The engineer-week estimates are not used. The "baseline/candidate" revision names are fine, but renaming them is optional.

## 14. Build decisions for develop

Al started the build at 08:09Z on 14 October. This section records his changes and the defaults chosen where his message left a detail open. It supersedes earlier sections where they differ. The numbered records SPEC-0082 and PLAN-0097 on develop carry the same content.

### Agents (D1 revised)

The chain now has six agent packages. The two probers are separate agents with separate evals, because a control and an exploit test fail in different ways and need separate scores.

| Agent | Stage | Job | Status |
| --- | --- | --- | --- |
| Grounding | 2 Ground | Report what human reviewers already concluded about similar prior issues, from the security graph | Placeholder: contracts, ports and stubs only |
| Investigator | 4 Investigate | Locate target and seam, write the control and exploit briefs, declare the component to build | Build |
| Builder | 5 Build | Find a setup recipe for the declared component; trusted replay must pass one native baseline test | Build |
| Control Prober | 6 Probe | Write the benign control test from its brief. It carries no token and must pass | Build |
| Exploit Prober | 6 Probe | Write the security regression test from its brief, with the run token as the security assertion's failure message | Build |
| Reviewer | 7 Review | Outcome-blind validity of each frozen test per revision | Build |

The stage order is Intake, Ground, Select, Investigate, Build, Probe, Review, Execute and Decide, as amended by A1. The two probers share code where the work is the same: the probe-protocol skill, the framework skills, the test-file write tool and the draft contract. Each has its own AgentSpec, instructions, output check, budget, provider key, eval set and baseline. Neither ever sees the other's brief, draft or result.

### Grounding agent placeholder

- **Intake gains Azure DevOps work items** as a second source behind the same intake port. A GitHub issue stays the first source. A work item becomes a case through an operator field map (deployment data, not code), the scanner header parser, and graph backfill of a missing file, line or CWE. A work item that establishes no repository is skipped and listed, never guessed. A person is never recorded as the source tool. Write-back to ADO stays out of scope, since editing tickets is a non-goal.
- **Grounding reads a context trusted code assembles.** The context holds the issue, its review comments, decided neighbours by CWE and by similarity, and a list of every retrieval that failed. The agent writes a brief: a short summary, precedents with verbatim quotes, an optional prior disposition, and caveats. A trusted citation check drops any precedent whose issue id or quote is not in the retrieved text, and records the drop as a caveat.
- **The brief is advisory.** It goes into the report for a person to read. No later stage reads it and the rule table never uses it. A prior human disposition of the same issue is in effect a label, so passing it to the Investigator or the probers would leak a label into the evidence. D10 below asks whether that should change later.
- **Only a placeholder for now.** The build adds the contracts, two ports (work-item source and security graph), in-memory fixture stubs and a Grounding eval on a fixture graph that scores citation validity and caveats. With no graph configured, the stage records `degraded: not_configured`, produces no brief, and the chain continues. No ADO or graph connectivity is built.
- **Generic.** The chain never branches on the tracker. ADO is one adapter of the work-item source.

### Gates deferred

No platform gate runs until both of these hold:

1. At least three end-to-end runs reach the correct decisive label on both revisions, in at least three languages.
2. Every agent has a promoted baseline that tracks accuracy, latency and tokens, split by language and by eval type.

Deferred until then: the kind and OpenShell milestone gate, the witness, held-out scoring, upgrading matrix rows to `live`, and the failure-injection matrix as a merge condition. The matrix canaries and failure-injection fixtures still run as ordinary development tests where they are cheap.

These rules stay in force because they define correctness rather than gate it: the five labels, exactly two tests, evaluator-only oracles, held-out sets never tuned on, Docker as the only execution route, inference only through llm.almckay.io, and no credentials in containers.

CI on develop runs lint, type checks and the v2 unit tests only, with no image builds and no v1 suites. The target is under three minutes. The "Shorter CI with gates deferred" thread owns that change.

### Where v2 is built (D6 revised)

- All work lands on `develop`, created from main at 14715ea. PRs target develop and merge when CI is green, which Al has authorised. Main stays untouched until Al decides to replace it with develop.
- v2 is built as `src/corsair` on develop. The default is that the first build PR removes v1's source, tests and eval runners from develop. v1 keeps running from a main worktree to supply its comparison baseline. This keeps develop's CI short and avoids a later rename. Develop keeps the toolchain images, the runtime matrix, corpus and benchmark data, and the docs records.

### Runs, evals and benchmarks: one layout

Committed data:

| Path | Holds |
| --- | --- |
| `evals/e2e/<language>/<set>/<case-id>/` | Chain cases: `input.json` (agent-visible), `oracle.json` (evaluator-only), `case.json` (pins, source, licence). Corpus pairs, benchmark cases and fixtures all live here, as sets named `corpus`, `benchmark` and `fixtures` |
| `evals/<agent>/<language>/<set>/<case-id>/` | Per-agent cases in the same three files; `common` for language-free cases |
| `evals/baselines/<agent>/<set>.json` | Promoted baseline, committed, with metrics keyed by language and eval type |
| `deploy/runtime-matrix.yaml` | Images, framework rows, run templates, exit-code maps |

Run output (ignored by git):

| Path | Holds |
| --- | --- |
| `.runs/chain/<run-id>/` | One chain run: `run.json`, `stages/<nn>-<stage>/`, `workspace/<episode>/commands.jsonl`, `artifacts/<sha256>` |
| `.runs/evals/<agent>/<set>/<stamp>-<mode>/` | One eval run: `summary.json`, `comparison.md`, and one `stages/`-shaped folder per case |
| `.runs/campaigns/<id>/` | Run ids and the campaign report |

Every stage folder holds the same files: `input.json`, `output.json`, `transcript.jsonl` and `usage.json`. A chain stage can therefore be replayed as that agent's eval without conversion. `usage.json` has one shape everywhere: model requests, input and output tokens, tool calls, wall time, retries, and failures by layer. A missing value is null, never zero. Each root has an `index.jsonl`, and `corsair report` reads any of them.

There are four eval types:

- **scripted:** no model; checks contract and wiring.
- **replay:** a live model on recorded inputs.
- **live:** a live model with a real Docker workspace, used for the Builder and both probers.
- **e2e:** the whole chain on frozen cases.

A baseline holds, for each language and eval type: accuracy for each evaluator dimension, p50 and p95 latency, tokens and requests per case, and the terminal-reason counts. The command is `make eval AGENT= SET= [LANG=] [MODE=]`.

### Temporal and OpenShell (Approach 2)

- **Approach 2 throughout.** Trusted workers run the workflow and the agents. Each case gets its own throwaway workspace, and the worker never runs inside a sandbox.
- **One workflow per case.** It replaces the parent workflow and the child workflow per stage. Native `TemporalDurability` turns each model request and tool call into an activity.
- **Three task queues:** `model` with one slot, `workspace` and `control`. The campaign becomes 66 workflow submissions.
- **A retry class per operation.** Shell commands and probe runs execute once. Results travel as artifact references, not content. Worker versions are pinned per run.
- **One Workspace interface, two backends.** Docker and OpenShell both implement PydanticAI's Workspace interface; only Docker is used until the gates resume. A lost workspace fails that stage attempt and is rebuilt from the cached recipe. Cleanup is a scheduled sweep by ownership label.
- **Not adopted:** signals, updates, approvals, continue-as-new and payload encryption. Credential brokering and the policy prover are not adopted, and neither is the worker inside the sandbox.

### Open decisions

| # | Decision | Default until Al says otherwise |
| --- | --- | --- |
| D10 | May the Investigator read Grounding precedents, with their dispositions removed? | No, until Grounding has a baseline and its effect on the Investigator can be measured |
| D11 | Remove v1 from develop in the first build PR? | Yes; v1 baselines come from main |

### Corrections from review of SPEC-0082

The Codex review of PR #134 found three gaps. All three are fixed in SPEC-0082, and they supersede sections 5 and 13 where they differ:

- **Review comes before any execution that counts.** The run after freezing is now a mechanical check only. It keeps `ok`, `not_run` or `errored` and discards the outcome. The Reviewer reviews the final frozen bytes, and Execute runs only reviewed bytes.
- **A check marker attributes the failure.** Each test writes a check marker (`safe` or `unsafe`) immediately before its security assertion, and `assertion_failed` requires check `unsafe`. The token alone could not attribute a failure, because repository code can read and print it.
- **ERROR is scoped to the vulnerable revision.** An infrastructure failure on the fixed revision makes only the fix result `not_verified`. It no longer replaces a reproduced finding with ERROR.
- **Authors get only mechanical feedback.** A `not_run` result returns the author's full diagnostics, because the test body never started. An `errored` result returns only the exception type and the line in the author's own test file, because application code has already run. Every outcome of the check run has a defined next step, and the outcome table is read top to bottom with infrastructure exits first.
- **Every INCONCLUSIVE has its own reason.** R6 reports `probe_not_run`, `probe_errored`, `probe_anomalous` or `no_valid_observation`, and the fix result uses the same mapping.
- **Fourth review round (supersedes the two bullets above where they differ).**
  - Both tests carry the token in the assertion after their check marker, so a failed control assertion reads as `assertion_failed` and R3 records `control_failed` only then. Any other control outcome maps to `probe_not_run`, `probe_errored` or `probe_anomalous`.
  - For `not_run` and `errored` alike, authors get back only output lines that name their own test file, at most 20. Application code can run before the test body starts, for example in a fixture or a module import.
- **Fifth review round (supersedes the feedback rules above).**
  - Authors never get runtime output, because even a line that names their own file can carry the application's message. A not\_run or errored draft gets back its mechanical class and a fixed hint chosen from the exit class and the markers.
  - Authors also get the full output of the matrix row's optional syntax check, such as `python -m py_compile`, `node --check`, `ruby -c` or a test-compile step. That check runs no application code, and a row whose check could run code, such as `perl -c`, declares none.
  - R1 now covers every vulnerable-revision probe whose outcome is `infra`, so infrastructure failures always read as ERROR.
- **Review feedback loop (Al, 14 October; three reviews in total; supersedes "one revision" for review defects).**
  - A review round reviews the whole frozen pair, with at most three rounds: the first review and two re-reviews. Each author whose probe is invalid gets one revision per round, so at most two review revisions each, separate from the one mechanical revision. All of it spends the one total budget.
  - An author gets only its own probe's review: the failed check names, the Reviewer's defect text (at most four defects of 1 KiB) and citations that resolve to its own file or source it may read. It never gets a run result, the other probe's brief, draft or review, Grounding output or an oracle. Execute never runs inside the loop.
  - Each revision sets `revision_of`, re-freezes a new patch digest, re-runs the mechanical check on the changed draft and gets a fresh review of the whole pair. Reviews of an earlier digest never count.
  - Still invalid after three rounds or when the budget runs out: nothing executes and R2 gives INCONCLUSIVE (`test_invalid`).
  - Each round and revision is its own recorded step. A prober's `clean_attempt_rate` counts only drafts accepted at the first review; `accepted_within_limit` and the mean revision count measure the loop.
  - Example: the first live run's exploit probe patched `subprocess` globally instead of at the target's import site. The Exploit Prober now gets that defect and its citation, revises, and the pair is reviewed again.
- **PoV polarity (Al, 14 October; supersedes the security-regression form).**
  - The exploit probe is a proof-of-vulnerability (PoV) test, the DARPA Cyber Grand Challenge and Vul4J term: it passes on the vulnerable revision by demonstrating the reported condition, and fails on the fixed one.
  - The outcome classifier is unchanged. The check marker values are renamed `holds` and `violated`: whether the property about to be asserted is true.
  - R4: vulnerable control passed and PoV passed, and the PoV did not also pass on the fixed revision, gives LIKELY\_EXPLOITABLE. R5: PoV assertion\_failed (not demonstrated) on both independent attempts (D18) gives LIKELY\_NOT\_EXPLOITABLE with a sensitivity flag and its calibration listed. A PoV that passes on both revisions gives INCONCLUSIVE (`not_differential`).
  - Fix verified: R4, and on the fixed revision the control passed and the PoV is assertion\_failed.
  - A passing test is easier to make vacuous, so the Reviewer also checks that the PoV assertion could fail on code without the condition.
- **Proof-quality and scope decisions (14 October, D14 to D18).**
  - **D14, scope is provability (Al, 09:33Z):** a finding is in scope when both probes can prove it inside the workspace, deterministically and with no outbound network, using local stand-ins such as a local server, a temporary file or an in-process double. The Investigator returns `unsupported_scope`, naming what is missing, only when proof needs something the workspace cannot supply: a real remote endpoint, the host trust store, a system-wide policy or a specific library build. There is no vulnerability-category list anywhere.
  - **D15, counterfactual assertion:** the brief states `safe_observation`, what the test would see on a correct implementation, and the PoV assertion must be false there. Payload text echoed back in output, an argument list or a log is never proof.
  - **D16, structure or effect:** input merely reaching a dependency is never proof, because correct code usually passes input on as data rather than rejecting it. The PoV must show the input crossing from data into structure, or into an effect it should not have.
  - **D17, the Reviewer stays outcome-blind:** it judges whether each test is a valid experiment, never whether the code looks vulnerable. It must not call a PoV vacuous because the target looks safe, reject a control for not exercising the vulnerability, or steer an author toward what this code does.
  - **D18, LIKELY\_NOT\_EXPLOITABLE needs two failed attempts:** before R5 one independent second exploit attempt runs, reusing the first control unchanged under a fresh review, so the negative path runs three tests (two per attempt, revising D9); R5 only when both PoVs fail after positive reviews, and every R5 carries sensitivity: unverified until the corpus measures LNE precision per language and vulnerability class, then lne\_precision (Al, 11:26Z).

### Later changes on 14 October

These came after section 14 was written and supersede it where they differ.

- **Package path.** v2 was built in `src/corsair/v2` on develop (PR #133) and moved up to `src/corsair` on 2026-10-14 (PR #193) before the main cutover. Its matrix is `deploy/v2/runtime-matrix.yaml`.
- **Evals live inside each agent package.** Each agent is self-contained under `src/corsair/agents/<name>/`, holding `agent.yaml`, `agent.py`, `tools.py`, `skills/`, `evals/` (its cases and its promoted baseline) and a placeholder `release-policy.yaml`. The release policy is empty and enforced by nothing until the gates come back. Chain cases stay in `evals/e2e/<language>/<set>/<case-id>/`, and run output keeps the `.runs/` layout above.
- **CI is one job.** Until something runs end to end, develop's PR path runs a single offline job, `make test-v2`, with no model, and nothing else. The v1 shards, the image gate, the qualification and record guards all leave the PR path. They stay runnable by hand so they can return with the gates and release policies.
- **D10 and D11 are in force.** Al has not overridden either default. The Investigator does not read Grounding output, and the build's next PR removes v1 from develop.
- **The build must adopt the review corrections.** The contracts on develop still need two changes: a `check_marker` fact in `ProbeFacts`, and a `probe_anomalous` terminal reason. `unsupported_scope` joins the spec's terminal-reason list, matching the contracts.
- **This document is mirrored in the repository** as `docs/design/corsair-v2-proposal.md` on develop, so it can be reviewed on GitHub. That file is regenerated from this doc whenever the doc changes.
