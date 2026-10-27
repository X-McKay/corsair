# Evaluation gym

The evaluation gym answers one question repeatably: is this change better? It runs a frozen tier of composed cases through the same model route, trusted images and Temporal workflow that production uses, scores every episode on accuracy, evidence, tokens and time, and gates a candidate scorecard against a reference. The design and its work packages are recorded in [PLAN-0003](../plans/active/PLAN-0003-evaluation-gym.md); the improvement wave that drives these commands is the [gym-loop skill](../../.agents/skills/corsair-gym-loop/SKILL.md). Nothing here promotes a baseline or changes what counts as evidence.

Run every command from a synced checkout inside the Nix shell (`nix develop`, then `just sync`). The runner lives in [`entrypoints/gym.py`](../../src/corsair/entrypoints/gym.py); scoring, gate, capture, export and ledger live in [`evaluation/gym/`](../../src/corsair/evaluation/gym/).

## Tiers

Tiers are frozen `corsair.dataset/1` manifests whose entries are copied verbatim (same request and oracle paths and digests) from the existing manifests:

| Tier | Manifest | Cases | Use |
| --- | --- | --- | --- |
| `tier0` | [gym-tier0.json](../../evals/datasets/gym-tier0.json) | 6: one per language (Python `chain-python-cmdi-b`, and the JavaScript, Ruby, Java, Perl and C chain cases) | Smoke gate; a tier0 REJECTED stops a candidate early, but ACCEPTED needs tier1 |
| `tier1` | [gym-tier1.json](../../evals/datasets/gym-tier1.json) | 15: every runnable composed case (dev 3, safety 2, adversarial 2, chain 8) | The acceptance gate |

`corsair dataset validate evals/datasets/gym-tier0.json evals/datasets/gym-tier1.json` checks both. A holdout tier is filled only through reviewed intake and does not exist yet.

Holdout hygiene: a holdout tier is only held out if no family, family stem, chain pair or source tree it uses appears in another split. `just dataset-families evals/datasets/gym-tier0.json evals/datasets/gym-tier1.json` (adding `gym-tier2.json` once it exists) checks the tiers together and exits `1` on a family id or its `<language>/<class>` stem (so bare `xxe` under a Java recipe and `ih-java-xxe` collide), a case, a chain pair in any request layout (`<class>-a`/`<class>-b`, `…/v3/`, `…-v3`) or a source tree (same resolved path, same pair stem directory or same declared digest) that crosses splits; the rules are listed in the [baseline policy](../../evals/baselines/README.md#checking-the-family-grouped-split). A row that shares any of these with tier0 or tier1 belongs in tier1, not the holdout.

## Verify a candidate

`verify` gates tier0 in smoke mode (`--smoke` on `corsair gym gate`): a language regression or a token-ratio breach at tier0 stops the candidate, but the objective margin is only reported there, because every tier0 language already verifies and its margin is noise; tier1 is gated in full.

The standard candidate protocol is one command:

```bash
just -- gym-verify "<main checkout>/.runs/gym/reference"
corsair gym verify                     # the same, with the default reference
```

`corsair gym verify [--reference DIR] [--repeats 3] [--concurrency 2] [--skip-tier1] [--budgets FILE] [--temporal-address A]` runs tier0, gates it against `DIR/tier0.json`, and unless that gate is REJECTED runs tier1 and gates it against `DIR/tier1.json`. It prints both gate tables and ends with one line, `VERDICT: ACCEPTED`, `VERDICT: REJECTED` or `VERDICT: INCOMPARABLE`, exiting 0, 1 or 2. That line is also written to stderr in every output format, so a captured log always ends with it while `--format json` keeps stdout one JSON record. The final decision is REJECTED when either gate rejected, else INCOMPARABLE when either gate was incomparable, else ACCEPTED. `verdict.json` under `<gym root>/verify/<verify-id>/` is one [`VerifyRecord`](../../src/corsair/contracts/gym.py) (schema `corsair.gym-verify/1`): the candidate's `branch` and `commit` (from the runs' scorecards), the chain `decision`, `tier0` and `tier1` as `TierGate`s (reference scorecard path, candidate scorecard path, run directory and the gate verdict with its reasons, delta J, token ratio and per-language deltas), `skipped` (each tier not run, with `skipped_by_request` or `rejected_at_tier0`), `complete`, the `reference` directory, the sanitized `invocation` and `recorded_at`. `corsair gym ledger append --verdict` reads that file as is (see [Budgets and the ledger](#budgets-and-the-ledger)). `--reference` defaults to `<gym root>/reference` when it exists. `--skip-tier1` stops after tier0; its ACCEPTED is a smoke result, not an acceptance, and `verdict.json` says so (`complete: false`). `verify` holds the [run lock](#the-run-lock) once across both tiers, so no other run lands between them, and takes the same `--lock-timeout` and `--no-lock` switches as `gym run`.

## The shared run store

Gym runs persist in one directory shared by every worktree of the repository, so a run outlives the worktree that produced it and `replay`, `capture` and `runs` see runs from any worktree. The gym root is `<main checkout>/.runs/gym/`, where the main checkout is the parent of `git rev-parse --git-common-dir` (in the main checkout itself this is its own `.runs/gym/`):

| Path | Holds |
| --- | --- |
| `store/` | The content-addressed artifact store of every gym run (`blobs/`, `operations/`) |
| `runs/<run-id>/` | One run directory each (below) |
| `reference/` | The current reference scorecards `tier0.json` and `tier1.json` read by `verify` |
| `verify/<verify-id>/verdict.json` | One record per `verify` |
| `lock/holder.json` | The [run lock](#the-run-lock)'s holder; present exactly while a run or `verify` holds it |

Settings whose `artifact_root` is not the default `.runs` keep that directory as the store and use `<artifact_root>/gym/` as the gym root; `--out DIR` still places a single run's directory anywhere. Concurrent runs from different worktrees cannot corrupt the store: every blob and operation record is written to a temporary file in its directory, fsynced and published with an atomic `link`, which fails rather than replaces when the name exists; an existing blob has the same content by construction (its name is its sha256), and an existing operation record with different content raises an identity conflict instead of being overwritten. Operation ids are derived from run ids, which carry a time stamp and a random suffix.

`corsair gym runs [--root DIR] [--tier T] [--limit N]` (`just -- gym-runs …`) lists stored runs newest first: run id, commit (`+dirty` when the working tree was), tier, repeats, sliced, J, macro verified accuracy, worst language, macro effective tokens, p50 seconds, capped-call episodes and run directory; `--format json` prints the same rows. While the run lock is held, the human and Markdown views start with one line naming its holder (run id, tier, branch and commit, pid and host, whether that process still runs, and how long it has held the lock). It also lists run directories placed directly under the root, the layout before the shared store.

To bring runs made before the shared store into it, copy their run directories and their worktree's store without overwriting anything: `cp -a <worktree>/.runs/gym/<run-id> <gym root>/runs/`, `cp -an <worktree>/.runs/blobs/. <gym root>/store/blobs/`, `cp -an <worktree>/.runs/operations/. <gym root>/store/operations/` (and `cp -a <worktree>/.runs/gym/reference <gym root>/`). Names are content or operation digests, so a name that already exists holds the same record.

### The run lock

Every live run shares one model endpoint, so overlapping runs skew each other's latency and can fail each other's activities (activity heartbeat timeouts under contention are not a property of either candidate). Live runs therefore serialise automatically; there is no marker file to wait for.

- `gym run` and `gym verify` take the lock `<gym root>/lock/holder.json` after the run is admitted (tier, selection, concurrency, `--temporal-address` namespace) and before any image build or Temporal server starts, and release it when the run ends, also when it fails or is interrupted (Ctrl-C). `verify` takes it once for both tiers.
- The holder file records the holder's run id (`verify-…` for a verify), pid, host, branch, commit, tier and start time. It is written whole to a temporary name and published with an atomic `link`, which fails rather than replaces; check, reclaim and publish run under an `flock` on `lock/.guard`, so two waiters cannot both take it.
- While a live process holds the lock the caller waits and logs one line, `gym.lock_waiting`, when the wait starts and every 60 s, with the holder's run id, how long it has held the lock and how long the caller has waited. After `--lock-timeout` (seconds or a duration such as `30m` or `2h`; default `2h`) it exits 2 with a refusal naming the holder; nothing was started.
- A holder whose pid no longer exists on this host is stale: the next caller reclaims it and logs `gym.lock_reclaimed` with the stale holder. A holder on another host is never judged stale, and a pid reused by an unrelated process keeps the lock until `--lock-timeout`; in both cases `corsair gym lock release --force` is the remedy once the holder is known to be gone.
- `run.json` records `lock`: `used`, `holder_run_id` (the run's own id, or the verify id it ran under), `waited`, `wait_seconds`, `waited_for` (each holder it waited for) and `reclaimed`. `wall_seconds` starts once the lock is held, so it never includes the wait.
- `corsair gym lock status [--root DIR]` prints the holder (or that the lock is free); `corsair gym lock release --force [--root DIR]` removes the lock whoever holds it and prints that holder, and refuses (exit 2) without `--force`.
- `--no-lock` exists only for scripted tests: such a run is not serialised with live runs and its timing is not comparable. The lock serialises runs that share a gym root; settings naming another `artifact_root` use that root's lock.

### Intake: drafting and freezing reviewed cases

A holdout tier is filled only through reviewed intake: an agent may draft cases, and only the owner's review decides which oracle is frozen. Two `corsair dataset` commands carry it, with the review sheet between them ([CLI reference](../reference/cli.md#dataset-draft-chain_dir)).

1. The operator writes a recipe template: one admitted `Recipe` member (its `kind` and operator fields) without `module_file` and without the callable (`function`, or `method` for Java), which drafting binds from each directory's `input.json`. The template is operator-owned, like the recipe of any request; no kind is invented, and a kind outside the `Recipe` union is refused. For the Python XXE pair a secret-disclosure template modelled on [`evals/datasets/intake/recipe-read-file.json`](../../evals/datasets/intake/recipe-read-file.json) is:

   ```json
   {"kind": "python.secret_disclosure/1", "payload_parameter": "document", "fixed_kwargs": {},
    "public_files": {"hello.txt": "hello"}, "expected_control": "hello",
    "allowed_exceptions": ["builtins.ValueError"]}
   ```

2. Draft into an ignored directory (never under `evals/`):

   ```bash
   corsair dataset draft evals/datasets/chain/python/xxe-a evals/datasets/chain/python/xxe-b \
     --recipe-template .work/intake/wave1/recipe-python-xxe.json --split held_out \
     --out .work/intake/wave1/draft
   ```

   Each directory becomes `<case id>/request.json` (title, file, line and callable from `input.json` only; `claim_scope` component; source and fixed source admitted in place under `evals/datasets/corpus/` with their snapshot digests) and `<case id>/oracle.proposed.json`, plus `draft.json` (`corsair.dataset-draft/1`, which no dataset loader accepts) and `review.md`. Case ids are `<provenance>-<language>-<directory>` and families `<provenance>-<language>-<class>`, with provenance `ih`, `pr`, `syn` or `unk`. The proposal is mechanical: every decisive verdict the kind can reach for a component claim (a clean negative only for a kind with a qualified auditor rubric), no expected verdict, and `expected_fix` `NOT_REQUESTED` unless a fixed source exists. Legacy `expected_label`, `expected_rule` and the case's truth type are copied into the draft as data and never mapped onto the oracle. Drafting reads no `README.md`, `manifest.json`, `submission.json`, `verification/` or legacy narrative, and runs the `dataset validate` checks on every row, listing failures as blockers.

3. The owner reviews `review.md` (a copy is fine) and fills only its last three columns per row: `accept` (freeze the proposal), `amend` (freeze the `oracle.json` they wrote beside the proposal) or `reject`; a reviewer name; and, optionally, the SHA-256 of the oracle file they reviewed.

4. Freeze:

   ```bash
   corsair dataset freeze .work/intake/wave1/draft --review .work/intake/wave1/review.md \
     --into evals/datasets/gym-tier2.json \
     --against evals/datasets/gym-tier0.json evals/datasets/gym-tier1.json
   ```

   It refuses (exit 2, nothing written) a row without a decision, an edited code-owned cell, a changed draft file, a reviewed digest that does not match, an accepted row that fails the dataset checks, a family, case, chain pair or source tree (stem or snapshot digest) that sits in another split in `--against` or the existing manifest, and more than 64 entries. Otherwise it appends the accepted and amended rows to the manifest (kept entries are unchanged), writes `<case id>.request.json` and `<case id>.oracle.json` in place beside the corpus (`evals/datasets/corpus/`, as for the existing Perl row, because admission refuses `..` in a source path) and exits 1 with the old (`none` for a new manifest) and new dataset digests: a new frozen cohort to review and commit, never a plain success. A manifest outside the evals tree (a scratch rehearsal) keeps absolute, machine-local sources under `<stem>/` and is validated with `--settings` naming that `source_root`.

Freezing changes the tier's digest, so the next gate over it needs a new reference run.

## Run a tier

```bash
just images-gym                       # optional: build the content-tagged images up front
just -- gym-run tier0 --repeats 3
just -- gym-run tier1 --repeats 3 --concurrency 2
```

`TIER` is a tier name (`tier0` resolves to `evals/datasets/gym-tier0.json`) or a manifest path. Settings default to the checkout's `.state/settings.json` (the live model route) when it exists; pass `--settings FILE` otherwise. Other switches: `--concurrency C` (at most the settings' `max_concurrent_activities`, so no work waits for a slot and skews timing), `--case ID` (repeatable) and `--lang python,c` (sliced runs, see below), `--budgets FILE` (default `evals/experiments/budgets.json` when present), `--out DIR` (default `<gym root>/runs/<run-id>/`), `--run-id ID`, and `--lock-timeout DURATION` and `--no-lock` (see [the run lock](#the-run-lock)).

What the runner does, in order:

1. Loads the manifest and filters entries in memory for `--case`/`--lang` (language is the recipe-kind prefix). A filtered run is `sliced` and is diagnostic only.
2. Takes the gym root's [run lock](#the-run-lock), waiting while another live run holds it.
3. Tags each language's trusted image by content and builds any missing tag (see [images](#content-addressed-images)).
4. Starts an ephemeral, headless, in-memory `temporal server start-dev` on a free loopback port with the namespace `corsair-gym` pre-created, and waits until it answers. With `--temporal-address A` it instead connects to that server and refuses to run unless the namespace `corsair-gym` already exists there; it never falls back to `default`.
5. Derives an in-memory copy of the settings with namespace `corsair-gym`, task queue `gym-<branch-slug>-<sha7>` (the checkout's branch and commit) and the content-tagged images, composes the production worker in-process with `compose_worker` on that queue, and submits the existing `EvaluationWorkflow` through the typed API. There is no second scheduler or loop.
6. Scores each returned result with the same row scorer as `corsair eval` (`evaluation.scoring.score_batch`) and writes three files in the run directory `<gym root>/runs/<run-id>/`: `report.json` (the `corsair eval` report shape), `trajectories.jsonl` (one scored episode per case and repeat) and `scorecard.json`. Beside them are `run.json`, written when the run starts and completed when it ends (the sanitized command line, git branch, commit and dirty flag, the store and gym root, tier, repeats, concurrency, selection, budgets source and digest, the lock record, start and completion times, wall seconds and episode count, and the scorecard's `run` context; no settings values or credentials), `budgets.json` (the exact bytes of the budgets file used, when one was) and the ephemeral server's `temporal.log`.
7. Stops the ephemeral server and releases the lock, also when the run fails, and prints the scorecard, the run directory, the store, the transport and the image ids.

The command exits 0 when every row has a stored result and 1 when any row is unavailable (an operational loss, not a measurement). A run that the gym refuses, or that fails before scoring, exits 2 like any other failed command.

### Content-addressed images

Each language's image is tagged `corsair-<lang>:<tag>`, where `tag` is the first seven hex digits of a sha256 over the sorted relative paths and bytes of the working-tree files in `deploy/<lang>/` and `src/corsair/adapters/sandboxing/drivers/<lang>/` (generated bytecode excluded). Working-tree content, not commits, is hashed, so an uncommitted driver edit gets a new tag. A missing tag is built with the same `docker build -f deploy/<lang>/Dockerfile -t … .` that `just images` uses, so unchanged inputs reuse the cached image and two worktrees never overwrite each other's tags. The run overrides `Settings.images` in memory and records each image id on the scorecard. `just images` keeps the `:0.1` tags for the demo and the documentation.

### Configuration identity

`Settings.identity`, which becomes each result manifest's `config_digest`, excludes the transport and storage fields `temporal_address`, `temporal_namespace`, `task_queue`, `artifact_root` and `source_root`; the scorecard records transport separately. A per-run queue or port therefore keeps the identity, while an image tag (and so any driver or Dockerfile change), a model, a limit or an evidence-policy change produces a new one. Results recorded before this change carry the older identity, which included those fields; see the [baseline policy](../../evals/baselines/README.md).

## Read a scorecard

`corsair gym score REPORT --dataset MANIFEST [--out DIR] [--budgets FILE]` rescores a saved report offline into the same two files. Its run block comes from the run directory's `run.json`, else from the scorecard beside the report (a run imported without `run.json`, for which `score` then writes one), else from `--run-id`, `--git-commit` and `--git-branch`; otherwise it names only the report and `score` warns on stderr that the run context is unknown. A scorecard records the run (branch, commit, namespace, task queue, concurrency, image ids), the dataset digest, the configuration identities seen, the budgets digest, the models, the repeat count and whether the run was sliced, and summarises per recipe kind and per language:

- Verified accuracy: a case is verified when it passed with a decisive verdict and valid evidence (or passed an oracle that expects an abstention) in more than half of its repeats; the language figure is the mean over its cases, so one flaky repeat in three cannot flip a case. Raw accuracy is the plain pass rate over repeats.
- Reward: 1 for passed and verified, 0 for an unresolved abstention or a [target-side exception](#target-side-exceptions), -0.5 for any other `ERROR` or `UNABLE_TO_RUN`, -1 for a forbidden label or wrong decisive verdict, plus an efficiency bonus (only when verified and usage is known and a budget exists) and small shaping penalties.
- Effective tokens: uncached input + 0.1 × cached input + 4 × output. Unknown usage stays unknown and earns no bonus.
- Seconds: agent seconds plus sandbox host seconds, reported as p50 and p95.
- Failure stops: the gate-ledger stop of each failed episode, counted; a target-side exception counts as `target_exception` instead of its ledger gate `execution_error`.

The headline `objective_j` is the macro reward plus half the worst language's verified accuracy.

### Reasoning markers

Each trajectory also records where the output budget went, as observations that no reward, verified flag, objective or gate reads: `thought_tokens` (the reported total, `null` when no call reported it), `thought_share` (thought over output tokens), `output_cap` (the per-call cap from the frozen request's `Budget.max_output_tokens`, which `request_digest` binds; results do not carry the budget), `capped_calls` (calls whose reported output reached that cap), `reasoning_cap_exhausted` (a capped call whose thought tokens filled its whole output) and `dominant_call` (position, episode index, output tokens and seconds of the largest call). Per kind and language the scorecard shows the case-mean thought share and the number of episodes with a capped call and with an exhausted cap, and the gate table shows the capped-episode delta per language. The counts stay unknown when a group has no cap or no per-call reports, so a scorecard written before the markers existed shows `unknown` until `corsair gym score` rescores its report. A call counts as capped when its reported output tokens reach the cap; on a route that reports reasoning outside the output count (ADK's native Gemini route) a capped call is not detected.

### Run identity and operational stops

Each trajectory carries `run_identity`, the full [`RunIdentity`](../../src/corsair/contracts/gym.py) read from its stored result's `RunManifest`: package version, configuration identity (`config`), each role's prompt, agent spec, output schema and runtime skills digests, the risk-assessment and budget-policy digests, the image id and each role's model. The scorecard's `run_identity` keeps every distinct value per component (images and budget policies differ per language and case), so a prompt- or skill-only change, which leaves `identity_digests` (the configuration identity) unchanged, is still visible. A result without a manifest, or a component an older manifest did not record, stays unknown.

A failed trajectory is `operational`, with an `operational_reason`, when its stop is a fault of the run rather than of the agents. The rule reads only code-owned gate names and the workflow's own timeout reason, never model text, and a recorded role `ERROR` (a payload that raised in the sandbox) always keeps an episode behavioural:

| Reason | Terminal stop in the gate ledger |
| --- | --- |
| `heartbeat_timeout`, `activity_timeout` | `execution_error` whose reason is `<phase>: activity Heartbeat timeout` (or `StartToClose`, `ScheduleToStart`, `ScheduleToClose`) |
| `episode_timeout`, `provider_temporary`, `operation_reconciliation` | the last round stopped at `episode_timeout`, `provider_temporary` or `operation-reconciliation` (a replay refused after an unconfirmed execution, i.e. a lost host) |
| `execution_cancelled` | `execution_cancelled` |
| `evidence_not_run` | the last round has no observation and the workflow ended with an `execution_*` stop |
| `result_unavailable` | the row has no stored result |

`provider_max_tokens`, `packet_too_large`, `provider_permanent`, `producer_abstained`, audit rejects, coverage misses, budget exhaustion and a payload-level `execution_error` stay behavioural. Operational episodes keep their `ERROR` reward and count against verified accuracy and J; this is visibility, not forgiveness. Per kind and language the scorecard counts `operational_episodes`, lists every operational case and repeat under `operational_stops`, and records `verified_accuracy_without_operational_failures`, the majority verified accuracy had each operational episode verified. `render_scorecard` shows the count column and the list.

The gate reports, without changing its decision, an `identity_changes` map (per component: changed, unchanged or unknown) printed as one `Identity changes:` line, and the per-language operational delta. When a regressed language would not regress against the baseline's verified accuracy had its operational episodes verified, the gate stays REJECTED, adds the reason `operationally_confounded` and names the language in `operationally_confounded_languages`, so the orchestrator orders a clean re-run before reading the regression. Identity differences never make a gate INCOMPARABLE.

### Target-side exceptions

The kernel keeps its `ERROR` verdict when a role raises (status `ERROR`, outcome `ERROR`); the gym separates, for its reward only, an exception the target raised from a fault of the harness. A trajectory has `target_exception: true` when its verdict is `ERROR` and every role that the terminal round admitted as `ERROR` has a stored raw receipt (`corsair.raw-evidence/1`, reached through the observation's evidence bundle) that shows a completed native run: a `corsair.driver/1` record for the same operation and role with outcome `ERROR`, junit status `ERROR`, `observation_kind=execution_error`, coverage reported for the recipe module with the bound finding line in `covered_lines`, `cleanup_confirmed`, and no `error` or `driver_error`. The rule reads the raw receipt, not the admitted `RoleObservation`, so it gives the same answer on results stored before and after the verifier keeps coverage on its `ERROR` observations.

Such an episode scores 0, like an abstention: neither a false label nor an infrastructure fault. Its failure stop is `target_exception`, it is never `operational`, and verified accuracy is unchanged (it did not verify). A sandbox fault without a driver record (for example `SandboxExecutionError`), a `driver_error`, an unconfirmed cleanup, an uncovered bound line, a missing or unreadable receipt, a round without an observation, or one errored role that fails the rule keeps the episode at -0.5; a forbidden `ERROR` label still scores -1. Per kind and language the scorecard counts `target_exception_episodes` and lists each case and repeat under `target_exceptions`; `render_scorecard` shows the count column and the list, and `render_gate` the per-language baseline, candidate and delta. A scorecard written before these fields reads them as unknown until `corsair gym score` rescores its report. Only `load_results` reads the receipts, so a caller that passes its own result mapping to `score_report` names no target exception.

## Gate a candidate

```bash
just -- gym-gate "<gym root>/reference/tier0.json" "<gym root>/runs/CAND/scorecard.json"
```

`corsair gym gate --baseline SCORECARD --candidate SCORECARD` prints the decision, its fixed reasons and a metric table, and exits 0 for ACCEPTED, 1 for REJECTED and 2 for INCOMPARABLE. ACCEPTED requires that no language's verified accuracy fell, that `objective_j` gained at least 0.01 and that macro effective tokens stayed within 1.10 × the baseline.

`--smoke` makes a smoke gate for a tier where every language already verifies, so its objective margin is noise from single flaky episodes: `objective_below_threshold` is still listed among the reasons but does not reject, and only a language regression, the token ceiling and the INCOMPARABLE conditions decide. The verdict records `smoke: true` and the view's header reads `Gate (smoke)`, so an ACCEPTED smoke gate is never read as an acceptance. Without `--smoke` the gate is unchanged. (`corsair gym verify` does not use smoke mode yet.)

INCOMPARABLE means the two scorecards answer different questions, so neither a win nor a regression can be read from them: different dataset digests, different budgets digests, a sliced run on either side, fewer than three repeats per case, or unknown token usage. Re-run both sides on the same tier, budgets and repeat count instead of reading the deltas.

## Replay, capture and export

`replay`, `capture` and `score` read results from the store the run directory's `run.json` names, else from the configured or shared store.

- `just -- gym-replay RUN-DIR CASE` (`corsair gym replay RUN-DIR --case ID`) prints each repeat's round timeline (stop, payload digest, abstention, audit decision and rule, role outcomes, sandbox seconds), the per-call tokens, tool result sizes and seconds from the stored usage, and the code-owned explanation of the verdict. It never prints payloads, hypotheses or model reasons; JSON output carries the same fields.
- `just -- gym-capture RUN-DIR CASE [--reference RUN-DIR …]` freezes every failed repeat of a case as agent fixtures and datasets under `evals/` and kernel replay cases under `tests/replay/kernel/`. The manifest is found by the report's dataset digest (or `--dataset`). A reference run over the same dataset may supply the demonstrated payloads for a case that flipped to failing.
- `corsair gym export-grpo --runs RUN-DIR … --out FILE` writes grouped rewards and group-normalised advantages with per-round proposals and identity digests; packets and reasoning are never written.

## Budgets and the ledger

- `corsair gym budgets --from SCORECARD --out FILE` derives per-kind token and time budgets from a scorecard's p95 values and prints their digest. Both sides of a gate must use the same budgets file.
- `just -- gym-ledger append --id ID --entry baseline|experiment [--wave N] [--track …] [--idea …] [--lesson …] …` appends one row to `evals/experiments/ledger.jsonl` ([`LedgerRow`](../../src/corsair/contracts/gym.py)). A row's `branch` and `commit` always name the candidate; every source that names them (`--branch`/`--commit`, the scorecards, a verify record) must agree, and a short commit agrees with its full form.
  - Baseline: `--scorecard S --tier T` records the scorecard's headline metrics. A baseline without a scorecard is refused.
  - Experiment with gates: `--tier0 RUN-DIR|SCORECARD` and `--tier1 RUN-DIR|SCORECARD` gate each candidate against `--reference-tier0`/`--reference-tier1` (a ledger row id or a scorecard path; default the latest baseline row of that tier) and record the reference, the scorecard, the run directory (when a directory was given) and the gate verdict with its ΔJ, token ratio and per-language deltas. `--verdict FILE` instead copies both tier gates and the candidate identity from a [`VerifyRecord`](../../src/corsair/contracts/gym.py), normally the `verdict.json` that `corsair gym verify` wrote (`just -- gym-ledger append --id ID --entry experiment --wave N --verdict <gym root>/verify/<verify-id>/verdict.json --decision …`); a tier the record did not run stays absent (`—`), and it cannot be combined with `--tier0`/`--tier1`. `--scorecard S --tier T --baseline REFERENCE` still gates a single scorecard.
  - Experiment without a scorecard (an offline dx change): `--branch B --commit C` alone.
  - `--decision accepted|rejected|inconclusive|merged` records the orchestrator's decision; `merged` requires `--merge-commit SHA`, and only `merged` takes one.
  - Refusals exit 2 with a fixed message and leave the ledger unchanged: an existing id, a baseline without a scorecard, a merged decision without its merge commit, disagreeing candidate identities, `--reference-tierN` without `--tierN`.
- `just -- gym-ledger render` regenerates the tables of `evals/experiments/LEDGER.md` below its hand-written header (everything above `## Baselines` is kept byte for byte). The Waves table shows, per experiment, id, track, `branch@commit`, the tier0 and tier1 gate (decision, reason codes, regressed languages), ΔJ and token ratio as `tier0 / tier1`, the decision (with the merge commit) and the lesson; `—` marks a value the row does not record. The rejected-ideas table lists rows whose decision is `rejected`. Lesson and idea text is printed as given on one line with pipes escaped; the contract bounds it at 500 and 300 characters.

## Limits

A runner test with scripted inference under real Docker and a real ephemeral Temporal server proves the lifecycle and the records, not model accuracy. A live tier run is a small-n diagnostic on one shared model endpoint: compare latency only at equal concurrency. Scorecards, run directories and the shared store under `.runs/` are private evidence; reference scorecards are copied under `evals/baselines/candidates/` only by the orchestrator, and nothing is promoted.
