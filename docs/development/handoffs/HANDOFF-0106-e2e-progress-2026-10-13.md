---
id: HANDOFF-0106
kind: handoff
title: End-to-end runs on 2026-10-13
status: recorded
updated: 2026-10-13
related: [SPEC-0067, PLAN-0073]
---

# End-to-end runs on 2026-10-13

A cross-thread snapshot taken at about 18:30Z. Each PR's own HANDOFF carries its detail (HANDOFF-0102 on #117, HANDOFF-0103 on #111, HANDOFF-0104 on #113, HANDOFF-0105 on #115, HANDOFF-0100 on #116; not yet on main); this record ties them together. Sources: the project chat and threads (marked "thread report" where a fact was not checked on GitHub) and GitHub PR heads read at 18:28Z. Times are UTC.

## Current state in brief

- **The chain runs end to end.** On the fixture, all four model stages ran live on `llm.almckay.io` through plain Docker. That route is risk-accepted and unqualified (#113). Three of the six Docker runs reached the right verdict (LIKELY_EXPLOITABLE). The other three failed because of the author's choice of security test, or because the assessment over-claimed. #117 fixes most of that.
- **Corpus accuracy is unmeasured.** Only one of the 42 corpus cases has run: `ih-python-pathtraversal`, through `corsair run`. It stopped at the environment stage with ERROR, before any finding. No corpus case has a result to compare with its `expected.json`.
- **No LIKELY_NOT_EXPLOITABLE outcome has been produced by a live run.** Every finding so far was reproduced or inconclusive. Twice the assessment proposed not_reproduced without the evidence for it, and only the gate stopped it. A correct negative verdict is the least-tested outcome Corsair has, and the most damaging one to get wrong. See [Validating accuracy across the corpus](#validating-accuracy-across-the-corpus-and-likely_not_exploitable-outcomes).
- **The product entry point is not on main yet.** That covers `corsair run` (#109), the labels (#109), the terminal display (#112), the Docker route (#113), runtime inference and the cohort (#115), and the verdict-gap fixes (#117). See the PR board for each one's state.

## Verified state

Main is `184e609` (merge of #97). This record changes only documentation.

### Al's directions today, in order

| Time | Direction |
| --- | --- |
| 14:26 | Close out the open PRs, import the eval corpus from `X-McKay/infosec-harness` `eval-corpus/`, and drive towards a full end-to-end run for each use case. |
| 16:54 | Do not change the approach. Stage order, runner core, required witness and runtime matrix rows stay as they are. Only the interaction pattern and how a run is started change. |
| 17:05 to 17:17 | A user gives an issue id or an issue JSON and the system runs end to end: `uv run corsair run --id <issue-id>` or `--issue-json <path>`. |
| 17:08, 17:11 | Keep it general across languages. Images carry only the language, test frameworks and pinned versions, nothing case-specific. |
| 17:15, 17:29 | Start the end-to-end runs and post progress in the project chat as it happens. |
| 17:22 | Use the locally hosted model `llm.almckay.io` only, for now. |
| 17:31 | Running on the main checkout is fine if it is easier than a worktree. |
| 17:36 | `corsair run` shows the stage, agent and activity (tool calls, retries) in the terminal, with clean formatting and colours. |
| 17:42 | Add a risk-accepted route outside kind and OpenShell for quicker iteration, prove it works, then fix the infrastructure. |
| 17:58, 18:02 | The headline result is a label: LIKELY_EXPLOITABLE, LIKELY_NOT_EXPLOITABLE, INCONCLUSIVE, UNABLE_TO_RUN, ERROR, with the stage and reason beneath it. 18:02: "This is good. Lets proceed, and see if we can get the desired label from the end-to-end runs." |
| 18:07 | "Please merge 109 if it is ready." |
| 18:09 | Do 5 to 10 runs on the Docker route before going back to OpenShell and kind. |
| 18:16 | Make sure LIKELY_NOT_EXPLOITABLE verdicts can also be reproduced reliably. |
| 18:21 | Commit and push progress and record it in a hand-off document (this record). |

Label mapping agreed in the chat (17:58 to 18:02; #109 implements it):

- LIKELY_EXPLOITABLE means the run completed and the finding was reproduced.
- LIKELY_NOT_EXPLOITABLE means the run completed and the finding was not_reproduced or refuted_in_scope.
- INCONCLUSIVE means the chain ran but the evidence did not settle it, including a model stage that ended blocked.
- UNABLE_TO_RUN means the run stopped before the model stages for a reason in the case: admission refused, runtime undetermined or unsupported, no route, environment not ready, or no fixed revision.
- ERROR means a harness, Docker, sandbox, provider or timeout failure, or a crash.

The three-part result stays beneath the label. It has execution, finding and fix parts. The label must come from the assessment's admitted final disposition when one exists, not from the gate's finding. That fix is still owed on #109 (see the PR board).

### Run ledger

All model stages ran live on `llm.almckay.io`, with nobody else on the model. Run 1 and run 2 are thread reports from the "Live end-to-end fixture run" thread.

| Run | Route and source | Result | Stage times (s): ident / plan / author / assess | Evidence |
| --- | --- | --- | --- | --- |
| run 1 | host route, main `666d496` | Stopped at authoring. The model called the withdrawn `write_test_file` tool, and with retries at 0 the stage crashed with `UnexpectedModelBehavior`. | ident + plan 35 | RIG0 `.worktrees/claude/project-thread-e4c90r/.runs/fixture-e2e-20261013/live-002` |
| run 2 | OpenShell on a fresh kind cluster, `make qualify-fixture-e2e` | Every stage ran; inconclusive. The scripted control on the same cluster gave reproduced/verified. | 7 / 29 / 51 / 106 | `/mnt/project-files/e2e-run2.tar.gz` (provider fields redacted) |
| scripted-001 | Docker, #113 `da0667f` | Scripted control, completed reproduced/verified | — | `/mnt/project-files/e2e-docker-batch.tar.gz` |
| live-001 | Docker, #113 `da0667f` | reproduced/verified, admitted (LIKELY_EXPLOITABLE) | 4.5 / 29 / 22 / 28 | same tarball |
| live-002 | Docker | Inconclusive. The test wrote into a folder it never created and raised FileNotFoundError on both revisions. | 6 / 27 / 12 / 48 | same tarball |
| live-003 | Docker | reproduced/verified, admitted | 7 / 28 / 29 / 43 | same tarball |
| live-004 | Docker | reproduced/verified, admitted | 4 / 23 / 24 / 36 | same tarball |
| live-005 | Docker | reproduced/not_verified, admitted at that level. The test did not expect the fix's `ValueError`. | 9 / 30 / 57 / 64 | same tarball |
| live-006 | Docker | Stopped at authoring. There was prose before the JSON and the one correction was rejected. The test could not fail ("file unchanged"). | author 70 | same tarball |
| ih-python-pathtraversal-1 | `corsair run`, Docker, #109 `e90a8e3` merged with #115 (merge `cecc10d`) | **ERROR, stopped at environment**: environment budget exhausted, `total_tokens_limit 48000 (derived from 1 read windows and 13 work calls)`, 10 model requests in 13.5 s. The runtime row `cpython-3.12-pytest` was inferred, pytest was installed on both revisions, and cleanup was confirmed. | — | RIG0 `.worktrees/first-corpus-case/.runs/investigations/ih-python-pathtraversal-1` (not yet in the shared folder) |

On RIG0 the Docker batch lives under `/home/al/git/corsair/.worktrees/docker-route-live/.runs/fixture-e2e-docker/`. The tarball copies scripted-001 and live-001 to live-006 with provider fields redacted.

The run thread's variance table (18:20Z):

| Run | Route | Verdict | Admitted | Security test asserted | Author / assess (s) |
|---|---|---|---|---|---|
| run 2 | OpenShell | inconclusive | no | file still reads "outside" | 51 / 106 |
| live-001 | Docker | reproduced/verified | yes | raises `ValueError` | 22 / 28 |
| live-002 | Docker | inconclusive | no | raises `ValueError`, but setup broke | 12 / 48 |
| live-003 | Docker | reproduced/verified | yes | raises any exception | 29 / 43 |
| live-004 | Docker | reproduced/verified | yes | raises `ValueError` | 24 / 36 |
| live-005 | Docker | reproduced/not_verified | yes | result isn't "outside" | 57 / 64 |
| live-006 | Docker | stopped at authoring | – | file unchanged | 70 / – |

Live Docker runs reached the right verdict 3 times out of 6 (live-001 to live-006). Counting run 2, it was 3 of the 7 fully live fixture runs that reached a verdict stage. Run 1 stopped at authoring on the host route and scripted-001 is a control, so neither counts. Identification (4 to 9 s) and planning (23 to 30 s) were stable and no stage hit a tool limit. Both witnesses were admitted in every Docker run that executed tests. Run 2 on OpenShell did not get that: its baseline witness scored `witness_missing` (gap 7). Two things decide the rest: which security test the author chooses, and the assessment's over-claim.

### Gap list

| # | Gap | Seen in | Fixed or owned by |
| --- | --- | --- | --- |
| 1 | The fixture CLI needs an absolute `--evidence` path and the README did not say so | run 1 | #111 |
| 2 | A call to a withdrawn tool crashes authoring instead of ending it blocked | run 1 | #111 |
| 3 | The host route can never finish a live authoring run, because only the reviewed fixture bytes run on the host | run 1 | By design. The Docker route (#113) and OpenShell answer it. |
| 4 | The cluster runbook skips `make toolchain-images` before loading images | run 2 setup | #111 |
| 5 | The environment stage cannot run live on main because there is no real preparation adapter | runs 1 and 2 | Docker preparation on #109/#113; OpenShell preparation on #116 (needs the live gate) |
| 6 | The author's security test cannot tell the revisions apart (the skill's example of an absent effect suits writes, not reads) | run 2, live-006 | #117 |
| 6b | A security test must accept a refusal (exception or safe result) on the fixed revision | live-005 | #117 |
| 7 | The witness probe counted the test's own re-read as a deferred effect of the target, so the result was unknown and scored `witness_missing` | run 2 | #117 |
| 8 | The assessment over-claims not_reproduced because its skill never defines it | run 2, live-002 | #117. The not-exploitable thread is also writing the admission definition. |
| 9 | Authoring accepts a security test that raises in its own body on both revisions | live-002 | #117 |
| 10 | The authoring output parser fails on prose before bare JSON, and only one correction is allowed | live-006 | Open on #117. It needs live-006's raw `attempt-2-authoring.json`. |
| 11 | Authoring's development run shows only the control test's outcome, so a broken or unfailable security test is frozen unseen | live-002, live-006 | In progress on #117, as a witness check in the development run |
| C1 | The environment agent is not shown the file inventory or where the operator's smoke test is, so it probes for absent files | corpus case | Chain thread (thread report) |
| C2 | The environment token cap derived from "1 read window" (48,000) is too small, at about 4.8k input tokens per request | corpus case | Not yet assigned |
| C3 | A model stage that stops on its budget is labelled ERROR. The coordinator asked for INCONCLUSIVE, per Al's table. | corpus case | #109 (asked of the Node thread at 18:26Z) |
| C4 | Under Docker, the file list the environment agent needs for #115's smoke check (a whole-repository test listing) is not handed over from the Docker preparation | corpus case, #115 review | #109, as a Docker file-list hand-over commit (thread report) |

The gap numbers follow the chat. Gaps 6 to 11 are described in detail in HANDOFF-0102 on #117.

### PR board (GitHub heads at 18:33Z)

| PR | Head | State |
| --- | --- | --- |
| Merged since the 14:26 direction | — | #92, #95, #96, #73, #94, #98, #100, #102, #101, #91, #76, #99, #104, #103, #105, #108, #110, #106, #97 (`184e609`, current main) |
| #111 withdrawn-tool, CLI and runbook fixes | `1161e59` | Ready for Al's "merge". The main merge since `bceb544` resolved only `CURRENT.md` rows (thread report). |
| #112 terminal progress display | `df727c1` | Reported ready for Al's "merge" at `15b7e21` (review clean, CI green, no conflicts; thread report, 18:20). The head has moved since. |
| #109 issue entry, `corsair run`, labels, witness binding, relative paths | `0b6de48` | One review item left: a budget stop must be labelled INCONCLUSIVE (C3). The Docker file-list hand-over commit (C4) is also coming. Both are thread reports. Al's 18:07 merge word applies once the review is clean and CI is green. |
| #113 Docker route, recorded unqualified | `bf923bd` | Ready. Review was clean at `07cf90a` and only docs changed since (thread report). Merges right after #109 (Al said "merge" in its thread). |
| #115 runtime inference, smoke test, corpus-python cohort | `6295bdc` | Ready once CI finishes, no longer in rework (thread report). All 17 cohort repositories are minimal: `app.py`, `requirements.txt` and an empty tests folder. |
| #116 OpenShell preparation adapter (draft) | `81f6039` | Review clean. Waits on the live gate `make qualify-environment-preparation CORSAIR_NETWORK_RUN=<dir>` on RIG0 (Go 1.21+), after the Docker batch, on Al's word |
| #117 verdict gaps (draft) | `ab3b3d5` | Review clean (thread report). Gaps 6 to 9 are fixed; 10 and 11 are still open. Offline suite 1798 passed and scripted evals are clean (thread report). Live evals were not run, and the new probe digest is unqualified until `make qualify-witness`. |
| Coming | — | The `--id` path as its own PR (Node thread, local `f3824b8`). The not-exploitable fixture variant, corpus negative cases and commands (thread "Reproducing not-exploitable verdicts", branch `claude/not-exploitable-verdicts`): the scripted host run admits not_reproduced (thread report). |
| #118 this record | — | Merges on Al's 18:27 word once CI is green. |
| Outside today's e2e | — | #107 (Codex local results UI). Dependabot #71, #72, #78 to #81 and #114. |

## Validating accuracy across the corpus and LIKELY_NOT_EXPLOITABLE outcomes

Al asked (18:27Z) for the record to stress two needs. Accuracy must be validated across a larger part of the eval corpus. Above all, LIKELY_NOT_EXPLOITABLE outcomes must be correct. This section sets out what exists and what is missing, then proposes a plan. Nothing in it has been run yet.

### Why this matters most

- A wrong LIKELY_NOT_EXPLOITABLE tells an analyst to drop a real vulnerability. Corsair can make no worse error.
- No live run has produced a not_reproduced finding yet. Every live finding so far is reproduced or inconclusive.
- The assessment agent has already over-claimed not_reproduced twice (run 2 and live-002). Each time, only the deterministic gate refused it.
- The fixture batch tested only the exploitable direction. Today's 3 of 6 Docker runs says nothing about negatives.

### What the corpus can test today

The corpus (SPEC-0067, from infosec-harness `52aa2ac`) has 42 topics and 82 variants. 40 variants are `potentially_exploitable` and 42 are `likely_not_exploitable`. Of the negatives, 40 are the `neutralized` half of a pair, one is `unreachable` and one is `unknown`.

| Language | Topics | Development | Held out | Runner and row today |
| --- | --- | --- | --- | --- |
| Python | 22 | 17 (the #115 `corpus-python` cohort) | 5 | `cpython-3.12-pytest`, image-only |
| JavaScript | 9 | 7 | 2 | Some runtimes undetermined; SPEC-0067 lists Node's built-in runner and Vitest as needed |
| Perl | 6 | 5 | 1 | TAP row is image-only; Test2::V0 under `prove` is needed |
| Java | 3 | 3 | 0 | JUnit 5.10 is needed |
| C | 2 | 2 | 0 | No detector; a C toolchain with AddressSanitizer is needed |

**The current mapping hardly tests negatives.** SPEC-0067 maps each pair to one case. The exploitable variant is the baseline and the not-exploitable variant is the fix candidate, so the expected outcome is completed / reproduced / verified. That uses 40 of the 42 negative variants only to verify fixes. They never stand alone as a case whose correct headline is LIKELY_NOT_EXPLOITABLE.

Only two cases expect `completed / not_reproduced / not_applicable` in their `expected.json`. Both are unpaired development cases in the Python cohort: `ih-python-healthcheck` (unreachable) and `ih-python-queryhelper` (unknown). SPEC-0067 leaves the reverse mapping (the not-exploitable variant as its own baseline) as "possible later".

**Conflict to settle.** Neither unpaired case has a fixed revision. #109 refuses a request without `fixed_revision` at admission as UNABLE_TO_RUN (Node thread report). So the only two negative cases would end UNABLE_TO_RUN against an expected not_reproduced. Before any negative corpus result can count, either:
- `corsair run` accepts a request with no fixed revision and reports fix `not_applicable`, or
- these cases gain a candidate revision.

Al decides this, because it changes the issue request contract.

### When a negative verdict is admitted

The gate rule is in `core/disposition.py` `assess` on main, and #117 extends it:

- The gate allows the finding not_reproduced only when **every** baseline run is classified `safe`. A safe run means the control passed and the security test passed. It also means the witness shows the target path was reached, the planned effect absent, and the planned safe behaviour.
- A failed control, a contradiction between runs, no valid run, or incomplete repeats give inconclusive.
- With #117, a security test that contradicts its witness makes the run `unusable`. That is a test passing while the witness shows the effect (`security_passed_with_effect`), or failing while the witness shows the safe behaviour (`security_failed_with_safe_witness`).
- The assessment can lower the gate's result but never raise it. #117's assessment skill states that not_reproduced needs every baseline security test to pass, with the witness showing the sensitive path ran, the effect absent and the safe behaviour.
- The label comes from the admitted final disposition. LIKELY_NOT_EXPLOITABLE is completed plus not_reproduced or refuted_in_scope. No current case expects refuted_in_scope, because SPEC-0067 notes that testing cannot refute a claim.
- A run that stops before the gate is never LIKELY_NOT_EXPLOITABLE, whether the stop comes from setup, the environment, a budget, a crash or an author that blocks. #109's C3 fix maps a budget stop to INCONCLUSIVE.

Risks to check before trusting a negative verdict (inferred from the rule and not yet tested live):

- A test that never reaches the target passes trivially. It must be classified unusable, not safe, so `path_reached` must be true for a safe run. Check that an `unreachable` case such as `ih-python-healthcheck` can satisfy that at all: if the sink is unreachable by design, the planned target must be the entry point, not the sink.
- Gap 11's planned fix deliberately does not refuse a security test that passes on the reported revision, because that would make not_reproduced impossible. Keep that property in any later authoring change.
- The cohort repositories are minimal (`app.py`, `requirements.txt` and an empty tests folder; thread report). So the baseline test is #115's operator smoke test, and the control's meaning rests on it.

### Scoring against `expected.json`

Each corpus case's `expected.json` holds an oracle: `stopped_at`, the gate's three parts and `assessment_admitted`. Score per run on the admitted final disposition, and report these terms separately, never folded into one accuracy number:

| Outcome | Definition | Target |
| --- | --- | --- |
| **False negative** | LIKELY_NOT_EXPLOITABLE where the expected finding is `reproduced` (a real vulnerability dismissed) | **Zero.** Any one is a release blocker. |
| **False positive** | LIKELY_EXPLOITABLE where the expected finding is `not_reproduced` | Zero on the negative fixture; measured and reported per cohort |
| True positive / true negative | The headline matches the expected finding | Reported per cohort and direction |
| Abstention | INCONCLUSIVE, UNABLE_TO_RUN or ERROR on a case that expects a completed run | Reported by stop stage and reason. It is not wrong, but it counts against coverage. |
| False fix verification | fix `verified` where the expected fix is `not_verified` | Zero |
| Exact match | All of stopped_at, gate and assessment_admitted equal the oracle (#97's match rule) | Reported alongside |

Report negatives and positives as separate rates, because 3 of 6 on the exploitable fixture hides 0 negative cases run. Each case runs once with a fresh run id and no retries. A diagnosed run that ran no test may run once more as its own attempt.

### Proposed validation plan

These steps follow the existing approach (stage order, runner core, required witness, matrix rows). Each step's runs go in the run ledger with evidence paths.

1. **Prerequisites.** Land #117, including items 10 and 11. Fix C1 and C2 in the environment stage, and land C4. Land #109 with C3, then #113 and #115. Settle the fixed-revision conflict above.
2. **Negative fixture.** The thread "Reproducing not-exploitable verdicts" is building a not-exploitable fixture variant. Its scripted host run admits not_reproduced (thread report). Run it fully live on the Docker route five times, interleaved with five runs of the exploitable fixture, so the same agent versions face both. Bar: 5 of 5 LIKELY_NOT_EXPLOITABLE admitted and zero LIKELY_EXPLOITABLE on the negative, with no regression on the positive.
3. **Python negatives as they stand.** `ih-python-healthcheck` and `ih-python-queryhelper`, once the fixed-revision question is settled.
4. **Reverse mapping for Python.** Generate the 15 development Python pairs reversed, with the not-exploitable variant as the baseline and an expected not_reproduced outcome. The corpus thread does this as an extension of SPEC-0067 with its own frozen `expected.json` files. Run them alongside the 15 forward pairs, which give the exploitable direction and fix verification. That makes 32 Python development cases: about 17 negative and 15 positive.
5. **Other languages, as runners and rows exist.** JavaScript (7 development topics), then Perl (5), Java (3) and C (2), forward and reversed.
6. **Held-out cases (8).** Run these only at a milestone on Al's call, never for tuning. Their ids stay out of `docs/development/`.
7. **Only after the Docker figures are stable:** the kind and OpenShell gate (#116) and qualified (`evidence: live`) reruns of a sample.

## Validation and blockers

- This record was not checked by any command beyond `git` and the GitHub reads above. The run results are thread reports, backed by the tarballs where cited. The corpus case evidence exists only on RIG0.
- Every Docker run is **unqualified (risk accepted)**. No `evidence: live` qualification follows from them.
- Blockers: #109's owed fixes come before its merge and #113's. #117's items 10 and 11 gate the verdict rate. C1 and C2 stop every corpus case at environment until they are fixed.
- Corpus accuracy has not been measured: 1 of 42 cases ran, and it ended ERROR at environment. Negative accuracy has not been measured at all: no live not_reproduced so far, and the current mapping has only two negative cases, both of which #109 would refuse as UNABLE_TO_RUN. See the section above.

## Decisions and next steps

### Run kit

The fixture under Docker uses #113, frozen at `da0667f`, in worktree `/home/al/git/corsair/.worktrees/docker-route-live` (`$D` below). Run it after `uv sync --locked`. Build the image first if it is missing with `make toolchain-images TOOLCHAINS=python`, and write its id to `.runs/fixture-e2e-docker/images.json` as `{"cpython-3.12-pytest": "sha256:..."}`.

```
PYTHONPATH=src:. .venv/bin/python -m evals.fixture_e2e.run --sandbox docker \
  --images $D/.runs/fixture-e2e-docker/images.json \
  --provider-config /home/al/git/corsair/.runs/fixture-e2e-20261012/provider.json \
  --stage-profiles $D/evals/fixture_e2e/stage-profiles.json \
  --live identification,planning,authoring,assessment \
  --evidence $D/.runs/fixture-e2e-docker/live-NNN
```

Leave out `--provider-config`, `--stage-profiles` and `--live` for the scripted control.

The corpus case `ih-python-pathtraversal`, as posted by the Node thread at 18:22:

```
W=/home/al/git/corsair/.worktrees/first-corpus-case
cd $W
git -C /home/al/git/corsair fetch origin claude/toolchain-node8-iqwqim
git -C $W merge --no-edit origin/claude/toolchain-node8-iqwqim
git -C $W merge-base --is-ancestor e90a8e3 HEAD && echo has-e90a8e3
uv sync --locked
mkdir -p $W/.runs
echo '{"cpython-3.12-pytest": "sha256:68f08d0e933760a96e97ccafb3604a11ebddd0779e04c355f3a552dcf332832b"}' > $W/.runs/images.json
CORSAIR_IMAGES=$W/.runs/images.json uv run --locked corsair run \
  --issue-json $W/evals/corpus/issues/ih-python-pathtraversal/issue.json \
  --provider-config /home/al/git/corsair/.runs/fixture-e2e-20261012/provider.json \
  --stage-profiles $W/evals/fixture_e2e/stage-profiles.json \
  --evidence $W/.runs/investigations/ih-python-pathtraversal-1
```

- If the merge conflicts in `src/corsair/composition/direct.py`, keep both sides. #109 adds `witness_from_recorders`; #115 adds the smoke-file inventory.
- Docker's bridge network must reach PyPI.
- Send back the summary line, which starts with the label, and `record.json`.
- A rerun needs a fresh evidence directory, for example `-2`.

### RIG0 rules

- Work only in `/home/al/git/corsair/.worktrees/<branch>`, and never switch branches in `/home/al/git/corsair` or in `corsair-live-e2e`. `git worktree add` may need Al or the allow rule `Bash(git worktree add:*)`.
- RIG0 cannot read `/mnt/project-files`. Everything it runs must be fetchable from GitHub, with the commands relayed word for word.
- Only one thread uses live inference at a time. Only one thread holds the kind cluster; the run thread holds it, still up in `.worktrees/claude/project-thread-e4c90r`.
- Run each case once with a fresh run id and no blind retries. A diagnosed failure that ran no test may run once more.
- Never print provider config or keys. Never share anything from `corsair-pr30`'s `.runs`.

### Next

The full corpus plan is in [Validating accuracy across the corpus](#validating-accuracy-across-the-corpus-and-likely_not_exploitable-outcomes). In short:

1. Finish #109's owed fixes, review, merge on Al's word, then merge #113.
2. Land #117's items 10 and 11. Fix C1 and C2 in the environment stage, then rerun the corpus case as `ih-python-pathtraversal-2`.
3. Join the not-exploitable fixture and negative corpus cases to the Docker batch. Run the 17-case Python cohort toward ten Docker runs.
4. After that, #116's cluster gate on Al's word.

### Waiting on Al

- "merge" for #111 and #112 (recheck #111's moved head first).
- The word for #116's live gate.
- "close them" for the Dependabot PRs.
- Whether to keep the UNABLE_TO_RUN name.
- Whether a request with no fixed revision runs with fix `not_applicable` or is refused. This decides whether the two unpaired negative cases can be scored.
- Whether to add the reverse mapping (the not-exploitable variant as baseline) to the corpus cases.

## Continuation prompt

```text
Read AGENTS.md, docs/development/CURRENT.md and this handoff, then the HANDOFF records on #109, #113, #115, #116 and #117. Verify each PR's head and CI on GitHub before acting, since heads moved during the day. Next bounded action: get #109 review-clean (label from admitted final disposition, crash traceback and stage, budget stop as INCONCLUSIVE), merge it and #113 on Al's standing word, then rerun ih-python-pathtraversal on RIG0 through `corsair run` once the environment stage's inventory and budget gaps (C1, C2) are fixed. Then follow the corpus validation plan in this handoff, with the negative fixture and LIKELY_NOT_EXPLOITABLE scoring first (false negatives must be zero). Keep to llm.almckay.io, one model user, worktrees only on RIG0, no blind retries. Record results and write a new handoff.
```
