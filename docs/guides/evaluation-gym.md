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

The standard candidate protocol is one command:

```bash
just -- gym-verify "<main checkout>/.runs/gym/reference"
corsair gym verify                     # the same, with the default reference
```

`corsair gym verify [--reference DIR] [--repeats 3] [--concurrency 2] [--skip-tier1] [--budgets FILE] [--temporal-address A]` runs tier0, gates it against `DIR/tier0.json`, and unless that gate is REJECTED runs tier1 and gates it against `DIR/tier1.json`. It prints both gate tables and ends with one line, `VERDICT: ACCEPTED`, `VERDICT: REJECTED` or `VERDICT: INCOMPARABLE`, exiting 0, 1 or 2. The final decision is REJECTED when either gate rejected, else INCOMPARABLE when either gate was incomparable, else ACCEPTED. `verdict.json` under `<gym root>/verify/<verify-id>/` records the reference, both candidate and reference scorecard paths, both gate verdicts (reasons, delta J, token ratio and per-language deltas) and any tier that was not run with its reason. `--reference` defaults to `<gym root>/reference` when it exists. `--skip-tier1` stops after tier0; its ACCEPTED is a smoke result, not an acceptance, and `verdict.json` says so (`complete: false`).

## The shared run store

Gym runs persist in one directory shared by every worktree of the repository, so a run outlives the worktree that produced it and `replay`, `capture` and `runs` see runs from any worktree. The gym root is `<main checkout>/.runs/gym/`, where the main checkout is the parent of `git rev-parse --git-common-dir` (in the main checkout itself this is its own `.runs/gym/`):

| Path | Holds |
| --- | --- |
| `store/` | The content-addressed artifact store of every gym run (`blobs/`, `operations/`) |
| `runs/<run-id>/` | One run directory each (below) |
| `reference/` | The current reference scorecards `tier0.json` and `tier1.json` read by `verify` |
| `verify/<verify-id>/verdict.json` | One record per `verify` |

Settings whose `artifact_root` is not the default `.runs` keep that directory as the store and use `<artifact_root>/gym/` as the gym root; `--out DIR` still places a single run's directory anywhere. Concurrent runs from different worktrees cannot corrupt the store: every blob and operation record is written to a temporary file in its directory, fsynced and published with an atomic `link`, which fails rather than replaces when the name exists; an existing blob has the same content by construction (its name is its sha256), and an existing operation record with different content raises an identity conflict instead of being overwritten. Operation ids are derived from run ids, which carry a time stamp and a random suffix.

`corsair gym runs [--root DIR] [--tier T] [--limit N]` (`just -- gym-runs …`) lists stored runs newest first: run id, commit (`+dirty` when the working tree was), tier, repeats, sliced, J, macro verified accuracy, worst language, macro effective tokens, p50 seconds, capped-call episodes and run directory; `--format json` prints the same rows. It also lists run directories placed directly under the root, the layout before the shared store.

To bring runs made before the shared store into it, copy their run directories and their worktree's store without overwriting anything: `cp -a <worktree>/.runs/gym/<run-id> <gym root>/runs/`, `cp -an <worktree>/.runs/blobs/. <gym root>/store/blobs/`, `cp -an <worktree>/.runs/operations/. <gym root>/store/operations/` (and `cp -a <worktree>/.runs/gym/reference <gym root>/`). Names are content or operation digests, so a name that already exists holds the same record.

## Run a tier

```bash
just images-gym                       # optional: build the content-tagged images up front
just -- gym-run tier0 --repeats 3
just -- gym-run tier1 --repeats 3 --concurrency 2
```

`TIER` is a tier name (`tier0` resolves to `evals/datasets/gym-tier0.json`) or a manifest path. Settings default to the checkout's `.state/settings.json` (the live model route) when it exists; pass `--settings FILE` otherwise. Other switches: `--concurrency C` (at most the settings' `max_concurrent_activities`, so no work waits for a slot and skews timing), `--case ID` (repeatable) and `--lang python,c` (sliced runs, see below), `--budgets FILE` (default `evals/experiments/budgets.json` when present), `--out DIR` (default `<gym root>/runs/<run-id>/`) and `--run-id ID`.

What the runner does, in order:

1. Loads the manifest and filters entries in memory for `--case`/`--lang` (language is the recipe-kind prefix). A filtered run is `sliced` and is diagnostic only.
2. Tags each language's trusted image by content and builds any missing tag (see [images](#content-addressed-images)).
3. Starts an ephemeral, headless, in-memory `temporal server start-dev` on a free loopback port with the namespace `corsair-gym` pre-created, and waits until it answers. With `--temporal-address A` it instead connects to that server and refuses to run unless the namespace `corsair-gym` already exists there; it never falls back to `default`.
4. Derives an in-memory copy of the settings with namespace `corsair-gym`, task queue `gym-<branch-slug>-<sha7>` (the checkout's branch and commit) and the content-tagged images, composes the production worker in-process with `compose_worker` on that queue, and submits the existing `EvaluationWorkflow` through the typed API. There is no second scheduler or loop.
5. Scores each returned result with the same row scorer as `corsair eval` (`evaluation.scoring.score_batch`) and writes three files in the run directory `<gym root>/runs/<run-id>/`: `report.json` (the `corsair eval` report shape), `trajectories.jsonl` (one scored episode per case and repeat) and `scorecard.json`. Beside them are `run.json`, written when the run starts and completed when it ends (the sanitized command line, git branch, commit and dirty flag, the store and gym root, tier, repeats, concurrency, selection, budgets source and digest, start and completion times, wall seconds and episode count; no settings values or credentials), `budgets.json` (the exact bytes of the budgets file used, when one was) and the ephemeral server's `temporal.log`.
6. Stops the ephemeral server, also when the run fails, and prints the scorecard, the run directory, the store, the transport and the image ids.

The command exits 0 when every row has a stored result and 1 when any row is unavailable (an operational loss, not a measurement). A run that the gym refuses, or that fails before scoring, exits 2 like any other failed command.

### Content-addressed images

Each language's image is tagged `corsair-<lang>:<tag>`, where `tag` is the first seven hex digits of a sha256 over the sorted relative paths and bytes of the working-tree files in `deploy/<lang>/` and `src/corsair/adapters/sandboxing/drivers/<lang>/` (generated bytecode excluded). Working-tree content, not commits, is hashed, so an uncommitted driver edit gets a new tag. A missing tag is built with the same `docker build -f deploy/<lang>/Dockerfile -t … .` that `just images` uses, so unchanged inputs reuse the cached image and two worktrees never overwrite each other's tags. The run overrides `Settings.images` in memory and records each image id on the scorecard. `just images` keeps the `:0.1` tags for the demo and the documentation.

### Configuration identity

`Settings.identity`, which becomes each result manifest's `config_digest`, excludes the transport and storage fields `temporal_address`, `temporal_namespace`, `task_queue`, `artifact_root` and `source_root`; the scorecard records transport separately. A per-run queue or port therefore keeps the identity, while an image tag (and so any driver or Dockerfile change), a model, a limit or an evidence-policy change produces a new one. Results recorded before this change carry the older identity, which included those fields; see the [baseline policy](../../evals/baselines/README.md).

## Read a scorecard

`corsair gym score REPORT --dataset MANIFEST [--out DIR] [--budgets FILE]` rescores a saved report offline into the same two files. A scorecard records the run (branch, commit, namespace, task queue, concurrency, image ids), the dataset digest, the configuration identities seen, the budgets digest, the models, the repeat count and whether the run was sliced, and summarises per recipe kind and per language:

- Verified accuracy: a case is verified when it passed with a decisive verdict and valid evidence (or passed an oracle that expects an abstention) in more than half of its repeats; the language figure is the mean over its cases, so one flaky repeat in three cannot flip a case. Raw accuracy is the plain pass rate over repeats.
- Reward: 1 for passed and verified, 0 for an unresolved abstention, -0.5 for `ERROR` or `UNABLE_TO_RUN`, -1 for a forbidden label or wrong decisive verdict, plus an efficiency bonus (only when verified and usage is known and a budget exists) and small shaping penalties.
- Effective tokens: uncached input + 0.1 × cached input + 4 × output. Unknown usage stays unknown and earns no bonus.
- Seconds: agent seconds plus sandbox host seconds, reported as p50 and p95.
- Failure stops: the gate-ledger stop of each failed episode, counted.

The headline `objective_j` is the macro reward plus half the worst language's verified accuracy.

### Reasoning markers

Each trajectory also records where the output budget went, as observations that no reward, verified flag, objective or gate reads: `thought_tokens` (the reported total, `null` when no call reported it), `thought_share` (thought over output tokens), `output_cap` (the per-call cap from the frozen request's `Budget.max_output_tokens`, which `request_digest` binds; results do not carry the budget), `capped_calls` (calls whose reported output reached that cap), `reasoning_cap_exhausted` (a capped call whose thought tokens filled its whole output) and `dominant_call` (position, episode index, output tokens and seconds of the largest call). Per kind and language the scorecard shows the case-mean thought share and the number of episodes with a capped call and with an exhausted cap, and the gate table shows the capped-episode delta per language. The counts stay unknown when a group has no cap or no per-call reports, so a scorecard written before the markers existed shows `unknown` until `corsair gym score` rescores its report. A call counts as capped when its reported output tokens reach the cap; on a route that reports reasoning outside the output count (ADK's native Gemini route) a capped call is not detected.

## Gate a candidate

```bash
just -- gym-gate "<gym root>/reference/tier0.json" "<gym root>/runs/CAND/scorecard.json"
```

`corsair gym gate --baseline SCORECARD --candidate SCORECARD` prints the decision, its fixed reasons and a metric table, and exits 0 for ACCEPTED, 1 for REJECTED and 2 for INCOMPARABLE. ACCEPTED requires that no language's verified accuracy fell, that `objective_j` gained at least 0.01 and that macro effective tokens stayed within 1.10 × the baseline.

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
  - Experiment with gates: `--tier0 RUN-DIR|SCORECARD` and `--tier1 RUN-DIR|SCORECARD` gate each candidate against `--reference-tier0`/`--reference-tier1` (a ledger row id or a scorecard path; default the latest baseline row of that tier) and record the reference, the scorecard, the run directory (when a directory was given) and the gate verdict with its ΔJ, token ratio and per-language deltas. `--verdict FILE` instead copies both tier gates and the candidate identity from a [`VerifyRecord`](../../src/corsair/contracts/gym.py) (`verdict.json`, schema `corsair.gym-verify/1`); it cannot be combined with `--tier0`/`--tier1`. `--scorecard S --tier T --baseline REFERENCE` still gates a single scorecard.
  - Experiment without a scorecard (an offline dx change): `--branch B --commit C` alone.
  - `--decision accepted|rejected|inconclusive|merged` records the orchestrator's decision; `merged` requires `--merge-commit SHA`, and only `merged` takes one.
  - Refusals exit 2 with a fixed message and leave the ledger unchanged: an existing id, a baseline without a scorecard, a merged decision without its merge commit, disagreeing candidate identities, `--reference-tierN` without `--tierN`.
- `just -- gym-ledger render` regenerates the tables of `evals/experiments/LEDGER.md` below its hand-written header (everything above `## Baselines` is kept byte for byte). The Waves table shows, per experiment, id, track, `branch@commit`, the tier0 and tier1 gate (decision, reason codes, regressed languages), ΔJ and token ratio as `tier0 / tier1`, the decision (with the merge commit) and the lesson; `—` marks a value the row does not record. The rejected-ideas table lists rows whose decision is `rejected`. Lesson and idea text is printed as given on one line with pipes escaped; the contract bounds it at 500 and 300 characters.

## Limits

A runner test with scripted inference under real Docker and a real ephemeral Temporal server proves the lifecycle and the records, not model accuracy. A live tier run is a small-n diagnostic on one shared model endpoint: compare latency only at equal concurrency. Scorecards, run directories and the shared store under `.runs/` are private evidence; reference scorecards are copied under `evals/baselines/candidates/` only by the orchestrator, and nothing is promoted.
