# PLAN-0003: evaluation gym and experiment loop (started 2026-10-26)

Cut from `main` at 12b1b14a after [PLAN-0002](PLAN-0002-improvement-loop-rounds-1-2.md). This plan adapts an external
"CorsairGym" proposal to Corsair's actual architecture and the rules in [AGENTS.md](../../../AGENTS.md). The
proposal's dual-loop idea is kept: an inner loop that scores single verification episodes on accuracy, evidence, tokens
and time, and an outer loop in which isolated worktree agents (Claude Code or Codex) propose one bounded change each and
a deterministic gate decides. Everything that assumed a model-driven sandbox shell, a `TwinSandbox`, Rust/Go/TypeScript
runtimes or `uv run pytest` is dropped or mapped onto what exists.

## Intent

Give the project one repeatable, production-faithful way to answer "is this change better?": the same model route,
Docker images and Temporal workflow that production uses, run over frozen case tiers, scored into one scorecard, and
gated against the last reference scorecard. Every experiment, accepted or rejected, is recorded once with its numbers
so no failed idea is retried blindly, every failure becomes a frozen regression fixture, and new cases enter through a
reviewed intake. The contract is the CLI and its exit codes, so any agent harness can drive it.

## Goals, non-goals, anti-goals

Goals: live-by-default evaluation (`hosted_vllm/` Qwen route, real images, real Temporal in a dedicated namespace);
per-episode telemetry on the existing records; one scorecard and one gate; a self-contained runner usable from any
worktree; failure-to-fixture capture; an append-only machine ledger; grouped reward export for later training.

Non-goals: fine-tuning itself; new languages or recipe kinds; promoting any baseline; changing what counts as evidence.

Anti-goals (a result that violates these is a failure even if numbers improve): a second agent loop, scheduler, tracing
stack or replay engine beside the workflow; model-authored execution or assertions; oracles or outcomes reaching agent,
tool or workflow inputs; a negative verdict from a failed reproduction; usage reported as zero when unknown; weakened
sandbox limits, source admission or cleanup; evaluators outside the installed package; experimenter agents seeing
holdout results.

## Mapping the proposal onto Corsair

| Proposal | Corsair |
| --- | --- |
| Episode `reset`/`step` with `exec_twin_cmd` | One `InvestigationWorkflow` run over a dataset entry; the producer proposes a JSON payload, trusted drivers run control, adversarial and fix revisions, the kernel decides. The gym scores the `InvestigationResult` and never drives the agent. |
| Two-phase oracle (`v_proof`) | The kernel's own gates (evidence valid, target line covered in both runs, differential, audit ACCEPT, fix check). `verified` = row passed and the verdict is decisive with valid evidence, or the oracle expects abstention and the verdict is not forbidden. |
| Labels VULNERABLE/PATCHED/BENIGN | Dataset `Oracle` (`expected_verdict`, `acceptable_verdicts`, `forbidden_verdicts`) and `Verdict`. Oracles stay in the manifest and are read only by the scorer. |
| Languages python, rust, cpp, go, typescript, java | The six runtimes on main, derived from the recipe-kind prefix: python, javascript, ruby, java, perl, c. |
| `FailureTaxonomy` enum | The existing gate ledger (`corsair.evaluation.ledger`) `failure_stops` names. No new enum. |
| `evals/gym/*.py`, `evals/tests/` | `src/corsair/contracts/gym.py` (models), `src/corsair/evaluation/gym/` (scoring, gate, capture, export), `src/corsair/entrypoints/gym.py` (runner), `tests/unit/evaluation/`. |
| `evals/trajectories/`, `evals/results/` | `.runs/gym/<run-id>/` (private evidence). Reference scorecards under `evals/baselines/candidates/gym-<date>-<sha7>/`; nothing is promoted. |
| `evals/EXPERIMENT_LEDGER.md` | `evals/experiments/ledger.jsonl` (machine, append-only) rendered to `evals/experiments/LEDGER.md`. |
| `uv run pytest`, `python -m evals.gym.cli` | `nix develop -c just …` and `corsair gym …`. |

## Design

### 1. Telemetry on existing records (trusted code only)

- `Usage` (`contracts/common.py`) gains `cached_input_tokens: int | None`, `thought_tokens: int | None`,
  `model_calls: list[ModelCall]` and `tool_calls_detail: list[ToolCall]`, each list capped at 64 entries (beyond the
  cap only the totals grow; `calls_truncated: bool`). `ModelCall` = index, input, cached input, output and thought
  tokens (`int | None` each), seconds. `ToolCall` = index, tool name, result bytes, truncated flag, seconds. Filled in
  `adapters/inference/adk.py` by the existing `before_model`/`after_model`/`before_tool` callbacks plus a new
  `after_tool` callback. ADK's LiteLLM path reports absent cached tokens as 0, so cached tokens are stored only when
  the provider reports a positive count; otherwise `None`, and the scorer never grants a cache discount for `None`.
  `usage_complete` stays the authority on whether totals are known. The 1 MB `InvestigationResult` cap is kept by the
  list caps.
- Sandbox timing travels through the raw receipt, because saved evidence is re-validated by rebuilding
  `RoleObservation` from the receipt (`steps/verification.py`). The trusted driver writes `wall_usec` (around the target
  run) and `cpu_usec` (from `/sys/fs/cgroup/cpu.stat`) into its receipt; `_validate_raw` admits them; `RoleObservation`
  gains `wall_seconds: float | None` and `cpu_seconds: float | None` (optional, so saved results still decode). Host-side
  create→wait seconds are recorded on `RoleObservation.host_seconds: float | None` by `docker.py`'s caller in
  `steps/verification.py`. `cpu_seconds` is driver-reported telemetry for efficiency scoring only and never
  participates in a verdict. Driver changes rebuild images, so this lands after the content-addressed image tags (§3).

### 2. Scoring (`contracts/gym.py` models, `evaluation/gym/` functions)

Pure functions over a report (`{rows, summary, dataset_digest}`), the dataset manifest and each row's stored
`InvestigationResult` (loaded from the artifact root as `rescore` does).

- `Trajectory` (one per row and repeat): case id, kind, language, expected (from the oracle), verdict, disposition,
  execution status, `passed`, `verified`, `failure_stop`, per-round summary (payload identity, producer abstained, audit
  decision and rule, role outcomes, sandbox wall, cpu and host seconds), usage totals and per-call lists,
  `usage_known`, `effective_tokens: float | None`, `seconds: float | None`, `reward`, run id, identity digests, git
  commit, model ids.
- Reward table (complete): passed and verified → 1.0 (a passed abstention on a case whose oracle accepts
  INCONCLUSIVE counts as passed and verified); failed without a false label (abstained where a decisive verdict was
  expected, e.g. `chain-python-cmdi-a` today) → 0.0; `ERROR` or `UNABLE_TO_RUN` → -0.5; forbidden label or wrong
  decisive verdict → -1.0. Efficiency bonus only when passed and verified:
  `phi_tok = clamp(1 - ln(1+E)/ln(1+B_tok), -0.5, 0.5)` with `E = uncached_in + 0.1·cached_in + 4·out`,
  `phi_time = clamp(1 - T/B_time, -0.5, 0.5)` with `T = agent seconds + sandbox host seconds`;
  `reward = r_verdict + 0.25·phi_tok + 0.25·phi_time + shaping`; unknown usage → bonus 0 and `usage_known = false`.
  Shaping: -0.05 per repeated candidate payload, per `packet_too_large` and per `provider_max_tokens` ledger entry.
  Consequence: abstaining can only gain by replacing false labels (-1 → 0); it never beats a verified verdict.
- Budgets `B_tok`, `B_time` per kind come from a budgets file (`{kind: {effective_tokens, seconds}}`) whose digest is
  recorded on every scorecard; the gate requires equal budget digests. `corsair gym budgets --from SCORECARD` writes one
  from a scorecard's per-kind p95 values; the first live tier1 run of this loop seeds `evals/experiments/budgets.json`.
- Per-case aggregation over repeats uses the majority: a case is verified when verified in more than half of its
  repeats; language verified accuracy is the mean over cases of that majority flag; reward and tokens use means over
  repeats. One flaky repeat in three therefore cannot flip a case.
- `Scorecard`: run id, git branch and commit, dataset digest, behaviour identity digests seen, budgets digest, model
  ids, Temporal namespace and task queue, repeats, concurrency, sliced flag, image ids, per-kind and per-language
  summaries (cases, raw accuracy, verified accuracy, mean reward, mean effective tokens, p50/p95 seconds, failure-stop
  counts, usage-unknown count), `macro_verified_accuracy`, `worst_language_verified_accuracy`, `macro_reward`,
  `objective_j = macro_reward + 0.5·worst_language_verified_accuracy`, `macro_effective_tokens`, `macro_p50_seconds`.
- Gate `gate(baseline, candidate)`: `INCOMPARABLE` (exit 2) when dataset digests or budget digests differ, either run is
  sliced, or repeats are below `min_repeats` (default 3); otherwise `ACCEPTED` (exit 0) iff no language's majority
  verified accuracy regressed, `ΔJ ≥ 0.01`, and `macro_effective_tokens ≤ 1.10 × baseline`; else `REJECTED` (exit 1).
  Tier0 (one case per language) is a smoke gate only: a tier0 REJECTED stops a candidate early, but ACCEPTED requires
  tier1. Markdown output is code-owned text only.
- Capture `capture(run_dir, case_id)`: writes a frozen agent fixture (producer and auditor packets and outputs with
  digests, in the `evals/fixtures` form the `eval-agent` datasets consume) and a kernel replay case (rounds and
  observations with the expected verdict) for `tests/replay`. Used on every failed or flipped case; the resulting
  fixture datasets are the fast, model-free regression guard.
- Export `export_groups(run_dirs, out)`: groups trajectories by case id across runs and repeats and writes JSONL with
  reward, group-normalised advantage, per-round payload proposals and audit decisions, plus the request digest and
  identity digests from which `corsair agent preview` rebuilds the exact model inputs deterministically. No packets or
  reasoning are stored in results. Groups with fewer than two members or zero reward variance are skipped.

### 3. Runner, images, identity and tiers

- `corsair gym run TIER [--settings S] [--repeats N] [--concurrency C] [--temporal-address A] [--case ID …]
  [--lang L,…] [--budgets F] [--out DIR]` (`entrypoints/gym.py`): resolves `TIER` to `evals/datasets/gym-<tier>.json`;
  starts an ephemeral `temporal server start-dev` on a free port with namespace `corsair-gym`, or uses
  `--temporal-address` only if that server already has the namespace (never `default`); composes the existing worker
  in-process (`entrypoints/worker.py`) on task queue `gym-<branch-slug>-<sha7>`; runs the existing `EvaluationWorkflow`
  through `entrypoints/api.py`; writes `report.json`, `trajectories.jsonl`, `scorecard.json` under
  `.runs/gym/<run-id>/`. `--case`/`--lang` filter in memory and set `sliced: true` (diagnostic only).
- Images are content-addressed: `just images` and the runner tag each image `corsair-<lang>:<tree7>` where `tree7` is
  the git tree hash of `deploy/<lang>/` plus that language's driver directory; the runner overrides `Settings.images`
  in memory for the run and records image ids on the scorecard. Unchanged content reuses the cached image; two
  worktrees never overwrite each other's tags. The `:0.1` tags remain for `just demo` and documentation.
- Identity: `Settings.identity` excludes transport and storage fields (`temporal_address`, `temporal_namespace`,
  `task_queue`, `artifact_root`, `source_root`) so a per-run queue or port does not change the configuration identity;
  the scorecard records transport separately. This changes the identity of past runs; none is promoted, and the change
  is noted in the changelog and `evals/baselines/README.md`.
- Tiers are frozen `corsair.dataset/1` manifests: `gym-tier0.json` = one case per language (python cmdi-b, the
  javascript, ruby, java, perl and c chain cases; 6 entries); `gym-tier1.json` = every runnable composed case today (15).
  `gym-tier2.json` (holdout) is filled through intake (§4) and is run only by the orchestrator and `eval-auditor`;
  experimenter agents never see its per-case results.
- `just` recipes: `gym-run TIER *ARGS`, `gym-gate BASELINE CANDIDATE`, `gym-replay RUN CASE`, `gym-capture RUN CASE`,
  `gym-ledger *ARGS`.

### 4. Outer loop, harness-neutral

- The protocol lives once in `.agents/skills/corsair-gym-loop/SKILL.md` (tracked; read by Codex and Claude Code).
  `.claude/commands/optimize-loop.md` and `.claude/agents/*.md` are local pointers to it with harness specifics
  (worktree isolation, tool lists). A Codex prompt file can point at the same skill.
- The contract is CLI exit codes, so no agent reproduces a judgment: `gym run` → scorecard; `gym gate` → 0/1/2;
  `gym capture` → fixture; `gym ledger append` → one JSONL row (`id`, branch, commit, tier, dataset digest, identity
  digests, budgets digest, verdict, deltas, lesson) and `gym ledger render` → `LEDGER.md`.
- Wave: (1) reference run of tier0 and tier1 at 3 repeats on the integration HEAD if none is recorded; (2)
  `eval-auditor` clusters failure stops and proposes 2 to 3 hypotheses with disjoint file scopes, checking the rejected
  table first; (3) one worktree agent per hypothesis runs `just test`, `just check`, the gates its scope needs, then
  tier0 and, unless rejected, tier1, and returns the gate table and branch; (4) accepted branches merge `--no-ff` one at
  a time into the integration branch, each re-gated against the new HEAD; after the wave tier0 re-runs on HEAD and
  becomes the new reference; (5) every failed or flipped case is captured as a fixture; (6) the ledger row is appended.
  Hygiene: the agent that mines cases in a wave does not tune prompts in that wave; one shared vLLM, so latency is
  compared at equal concurrency and `cpu_seconds` is the contention-resistant figure.
- Intake: a case-mining agent proposes `request.json` and `Oracle` files for new cases (starting from the 126
  un-manifested chain directories and `docs/reference/corpus/<lang>.md`); `dataset validate` checks them; the owner
  reviews each oracle before it is frozen into tier2. Agents never author oracles into a tier on their own.
- Automation: a scheduled task (Claude Code scheduled task or Codex cron) on the host that has the vLLM endpoint and
  Docker runs one wave nightly; tier2 runs weekly for drift. No new scheduler is written.

## Work packages and file scopes

| WP | Scope (exclusive) | Done when |
| --- | --- | --- |
| WP1a model telemetry | `contracts/common.py`, `adapters/inference/adk.py`, `tests/unit` for both | Per-call lists populated on a scripted episode and on one live `eval-agent producer-dev` run; caps enforced; `just test`, `just check` pass |
| WP2 gym core | `contracts/gym.py`, `contracts/__init__.py` exports, `evaluation/gym/{scoring,budgets,gate,capture,export,render,ledger}.py`, `tests/unit/evaluation/test_gym_*.py` | Tests pass: correct-but-INCONCLUSIVE gets 0; passed abstention gets 1; unknown usage gets no bonus; single-language regression rejected; digest or budget mismatch and sliced runs INCOMPARABLE; majority-of-3 absorbs one flaky repeat; capture round-trips through the existing fixture loader |
| WP3 runner, images, identity, tiers, CLI | `entrypoints/gym.py`, `entrypoints/cli.py` (`gym` subparser), `settings.py` (identity), `steps/manifest.py` if needed, `justfile`, `evals/datasets/gym-tier0.json`, `gym-tier1.json`, `evals/experiments/budgets.json`, `docs/guides/evaluation-gym.md`, `evals/baselines/README.md` note, `CHANGELOG.md`, runner tests under `tests/workflow` or `tests/integration` with scripted inference | `corsair gym run tier0` completes under Temporal and Docker on scripted inference; one live tier0 run produces a scorecard; content-addressed images verified |
| WP1b sandbox telemetry | `contracts/evidence.py`, `adapters/sandboxing/docker.py`, `adapters/sandboxing/drivers/*`, `steps/verification.py`, `deploy/*` if receipts change, `tests/integration` Docker tests | `wall/cpu/host` seconds present on a real Docker role run; saved-evidence re-validation still passes; `just test-docker` passes; new image ids recorded |
| WP4 loop assets | `.agents/skills/corsair-gym-loop/SKILL.md`, `.claude/commands/optimize-loop.md`, `.claude/agents/*.md`, `evals/experiments/LEDGER.md`, this plan | First reference scorecard recorded |

Order: WP1a ∥ WP2 → WP3 → WP1b → WP4 and the first reference run. WP1b waits for WP3 so driver rebuilds use
content-addressed tags and cannot contaminate parallel runs.

## Calls made by the orchestrator

- Gym contracts in `contracts/gym.py`, functions under `evaluation/gym/`, runner in `entrypoints/gym.py`.
- Majority-of-repeats per case for the gate; tier0 is a smoke gate only.
- Reward table completed as above; weights and clamps follow the proposal.
- Budgets self-calibrate from the first reference run and are pinned by digest.
- Transport and storage fields leave `Settings.identity`.
- Content-addressed image tags.
- Export ships digests, not packets; inputs are rebuilt with `corsair agent preview`.
- Tier2 is filled only through reviewed intake.

## Owner decisions still open

1. Integration branch and publication: accepted branches merge locally into `gym/loop` (cut from `main`); pushing or
   opening a PR to `main` happens only on explicit instruction per wave.
2. Whether the gate tolerance (majority-of-3) is acceptable, or a stricter paired rule is wanted at higher repeat counts.

## Record

- 2026-10-26: `.state/settings.json` created for the live route; `corsair doctor --model` passed `model_config`,
  `model_credentials` (no key required), `model_producer`, `model_producer_tools`, `model_auditor`; `worker_pollers`
  warned (no worker running). `nix develop -c just sync` exit 0. Builder check on this plan resolved: receipt path for
  sandbox timing, transport-free identity, content-addressed images, complete reward table, per-call list caps,
  `after_tool` as new work, budgets seeded from the first live run.
- 2026-10-26 WP1a merged (f1146a3d, branch `gym/wp1a-model-telemetry` d16a08b5). Gates in its worktree:
  `nix develop -c just -- test -q -W error` 1083 passed, 107 deselected (docker/temporal/live markers), 0 skipped, 0
  warnings; `nix develop -c just check` exit 0; `just build` ok (wheel resources not loaded outside the checkout
  separately); `dataset validate` on dev, producer-dev, auditor-dev, chain-python exit 0. Live
  `eval-agent producer producer-dev --repeats 1` on `hosted_vllm/Qwen3.6-35B-A3B-NVFP4`: exit 1, case01
  `candidate_exact_mismatch` (model behaviour, 0 operational failures); per-call entries present in the stored output
  (2 model calls: 2619/1179 and 3953/420 input/output tokens, thought 787 and 38, 11.8 s and 3.6 s; 2 tool calls).
  Provider reports reasoning tokens inside the output count; no positive cached-token count was reported, so
  `cached_input_tokens` stays None. Identity and fixture digests unchanged (Usage is outside both). Report rows still
  carry only totals; per-call lists live in the stored output artifact (row copying in `evaluation/agents.py` is WP2/WP3
  territory). Re-exports for `ModelCall`, `ToolCall`, `MAX_USAGE_CALL_ENTRIES` added on `gym/loop` (d0816f13).
- 2026-10-26 WP2 merged (bada655f, branch `gym/wp2-core` 4ddc51ec): `contracts/gym.py`, `evaluation/gym/{scoring,
  budgets,gate,capture,export,render,ledger}.py`, 7 unit test files. Its worktree gates: `just check` exit 0,
  `just -- test -q -W error` 1106 passed, 107 deselected, 0 warnings. Decisions recorded by the implementer: unknown
  tokens on either side make the gate INCOMPARABLE (not REJECTED); a correct decisive verdict with invalid evidence
  scores 0.0; capture writes fixtures only where trusted code can state the oracle (auditor fixture only against a
  validated covered differential, producer fixture only from a kernel-validated demonstrated round) and skips the rest
  with a reason; kernel cases are replayed before being written and never overwrite. On `gym/loop` after both merges:
  `just check` exit 0 (after sorting re-exports, 43de2bc6), `just -- test -q -W error` 1124 passed, 107 deselected.
  Docker, Temporal and live gates not run for WP2 (offline scope).
- 2026-10-27 WP3 merged (4915df02, branch `gym/wp3-runner` c7cb1371): `entrypoints/gym.py`, `corsair gym
  run|score|gate|replay|capture|export-grpo|budgets|images|ledger`, content-addressed image tags (sha256 over the
  working-tree bytes of `deploy/<lang>/` and the language's driver directory, first 7 hex), `Settings.identity`
  without transport/storage fields (`TRANSPORT_FIELDS`), `evals/datasets/gym-tier0.json` (digest 97fc4873…7501, 6
  cases) and `gym-tier1.json` (digest ec8cd985…bd17, 15 cases), `docs/guides/evaluation-gym.md`, just recipes
  `images-gym`, `gym-run`, `gym-gate`, `gym-replay`, `gym-capture`, `gym-ledger`. Worktree gates: `just -- test -q -W
  error` 1179 passed, 109 deselected, 0 warnings; `just check` exit 0; `just -- test-temporal -q -W error` 55 passed,
  11 skipped (docker-marked without CORSAIR_TEST_DOCKER), 109 s; `CORSAIR_TEST_TEMPORAL=1 just -- test-docker -q -W
  error` 59 passed, 1 skipped (long-probe opt-in), 103 s; `dataset validate` both tiers exit 0; `just build` ok.
  Runner integration test (scripted inference, real ephemeral Temporal, real Docker): server starts and stops,
  workflow in namespace `corsair-gym` only, queue `gym-<branch-slug>-<sha7>`, three files written, `sliced` with
  `--case`, refusal without the namespace. Live production path `just -- gym-run tier0 --repeats 1` on c7cb1371,
  `hosted_vllm/Qwen3.6-35B-A3B-NVFP4`, concurrency 2, 181 s: 6/6 `EXPLOIT_DEMONSTRATED` in one round, no failure
  stops, J 1.500, macro effective tokens 28874, per-language effective tokens python 20309, javascript 30242, ruby
  28355, java 21151, perl 37844, c 35342; agent p50 seconds 41.1 to 79.6 (sandbox seconds unknown until WP1b);
  repeats 1 so gate-INCOMPARABLE by design. Image ids equal to the `:0.1` ids (BuildKit cache hit, no from-scratch
  rebuild). That run directory lived in the WP3 worktree and was removed with it; later runs use the `gym/loop`
  worktree's `.runs/gym/`. Deviations: `corsair gym images` added; gym commands default to `.state/settings.json` and
  to `evals/experiments/budgets.json` when present (not created yet); `gym run` refuses `--concurrency` above
  `max_concurrent_activities`; the row-scoring loop is duplicated as `gym.score_batch` (dedupe candidate with
  `_handle_eval`). Not run: tier1, 3-repeat runs, no-cache image rebuild, `--temporal-address` success path, wheel
  install outside the checkout. On `gym/loop` after the merge: `just check` exit 0, `just -- test -q -W error` 1179
  passed, 109 deselected.
- 2026-10-27 WP1b merged (branch `gym/wp1b-sandbox-telemetry` ebc16f29): `RoleObservation.wall_seconds`,
  `cpu_seconds` (driver-reported, cgroup v2 `usage_usec`), `host_seconds` (create→wait, measured in `docker.py` and
  carried in the raw receipt as `host_usec` so saved-evidence re-validation can rebuild it); all six drivers emit
  `wall_usec`/`cpu_usec`; Docker tests resolve content-addressed tags via `trusted_images.py`. Worktree gates:
  `just -- test -q -W error` 1189 passed, 109 deselected; `just check` exit 0; `just -- test-docker -q -W error` 46
  passed, 14 skipped (Temporal-gated); with CORSAIR_TEST_TEMPORAL=1 59 passed, 1 skipped (long probe);
  `just -- test-temporal -q -W error` 55 passed, 11 skipped. New image tags python 00cb018, javascript 2c776a9, ruby
  f656e91, java c53d3d6, perl 709226b, c 2dd1ca8. Live `gym-run tier0 --repeats 1` on ebc16f29 (341 s, run under
  shared model load with the tier1 diagnostic): 5/6 pass, java ERROR (adversarial role ERROR after control held; the
  PLAN-0002 Java aim-variance item), all roles carry wall/cpu/host seconds; INCOMPARABLE to earlier runs (new images
  and identity). A result saved by 4915df02 decodes and re-validates with the three fields None.
- 2026-10-27 Diagnostic tier1 (not a reference): `just -- gym-run tier1 --repeats 3 --concurrency 2` on 8c4872c7
  (pre-WP1b), run dir `.runs/gym/gym-tier1-20261027t002030-1bcf3c` in the `gym/loop` worktree, identity b8d10250,
  dataset ec8cd985, 45 investigations, 40 min 58 s wall, exit 0, usage known for every episode, no cached tokens
  reported. J 1.2553, macro verified accuracy 0.967, worst language python 0.80, macro effective tokens 37,554,
  macro p50 65.7 s. Majority-failed cases: case02 (ERROR, NOT_DEMONSTRATED, ERROR) and chain-python-cmdi-a
  (INCONCLUSIVE ×3, `producer_abstained`). Failure stops: `provider_max_tokens` 4 terminal stops over 5 capped-call episodes (the earlier count of 6
  included inner rounds; corrected by h3's re-score; all
  python.secret_disclosure; a producer call spends the full 12,288-token output cap on reasoning, so the structured
  decision never completes), `producer_abstained` 6, `execution_error` 2 (case03 r0, java-xxe-b r1). Repeat variance:
  case02, case03, java-xxe-b, adversarial01, adversarial02. Top-5 token and seconds outliers are the capped-reasoning
  episodes (case02 r1 226,978 effective tokens, 485.7 s, 15 calls); thought/output ratio 0.905 run-wide; 4×output is
  71 % of effective tokens. Budgets derived from this run adopted as `evals/experiments/budgets.json` (a6e293f1);
  the python.secret_disclosure budget (174,386 tokens, 425.3 s) is inflated by those outliers. Hypotheses for wave 1:
  h1 (accuracy: reasoning-cap exhaustion on the producer call, `adapters/inference/adk.py`, possibly a reasoning
  control in `ModelSettings`), h2 (efficiency: producer instruction and source-grounding skill decisiveness,
  `agents/producer/instructions/system.md`, `agents/producer/skills/source-grounding/SKILL.md`), h3 (dx: thought-token
  share and output-cap marker on scorecard and trajectory rendering, `evaluation/gym/scoring.py`, `render.py`). Gates
  on `gym/loop` at a6e293f1: `just check` exit 0, `just -- test -q -W error` 1189 passed, 109 deselected.
- 2026-10-27 Wave-1 reference on 0697ff08 (identity 34f22f5e, budgets 63137bce, images python 00cb018, javascript
  2c776a9, ruby f656e91, java c53d3d6, perl 709226b, c 2dd1ca8, concurrency 2, no overlapping live runs): tier0
  `.runs/gym/gym-tier0-20261027t010807-479fc5` 18 episodes 811 s, J 1.4554, verified 1.0 all languages, macro
  effective tokens 37,512, p50 76.2 s (ruby varied: ED, ED, ERROR `execution_error`); tier1
  `.runs/gym/gym-tier1-20261027t012146-ade22e` 45 episodes 2126 s, J 1.4025, macro verified 0.9667, python 0.80,
  macro effective tokens 37,079, p50 57.9 s; majority-failed cmdi-a (INCONCLUSIVE ×3, `producer_abstained`) and
  safety01 (ERROR, ERROR, ED); varied: adversarial02 (r2 `provider_max_tokens`), case01 (r0 `execution_error`),
  case02 (r0 `provider_max_tokens` after a clean negative in round 3: 214,564 effective tokens, 601 s), safety01.
  All four `execution_error` episodes across both tiers share one signature: one round, audit ACCEPT, control
  PROPERTY_HELD, adversarial ERROR "exploit did not run the target", stop `evidence_unverified` (wave-2 candidate).
  Sandbox seconds present on every episode that reached the sandbox (java host median 4.1 s, others 0.2 to 0.6 s).
  Ledger rows `ref-w1-tier0`, `ref-w1-tier1`; candidate record `evals/baselines/candidates/gym-20261027-0697ff0/`.
- 2026-10-27 h3 merged (7d637e28, branch `gym/h3-scorecard-reasoning-markers` f6455392; dx track, offline):
  `thought_share`, `output_cap`, `capped_calls`, `reasoning_cap_exhausted`, `dominant_call` on trajectories, kind,
  language and scorecard; render columns and gate delta. Proof of no semantic change: re-scoring the tier1 diagnostic
  reproduces every existing scorecard and trajectory field exactly (J 1.2553 etc.); new values python thought share
  0.857, 5 capped-call episodes, 4 exhausted. Worktree gates: `just test` 1200 passed, 109 deselected, 0 warnings;
  `just check` exit 0. Accepted on the dx criterion (no scoring change, gates green); the ledger CLI cannot record an
  experiment without a scorecard, so this row lives here (follow-up: allow scorecard-less dx rows).
- 2026-10-27 Capture on the wave-1 reference failures (`corsair gym capture`, no source change): 5 kernel replay cases
  under `tests/replay/kernel/` (cmdi-a r0-r2, case02 r0, adversarial02 r2; model prose redacted at capture) and 2
  producer fixtures with datasets (case01 from its demonstrated repeats; tier0 ruby-pathtraversal from its own r0/r1;
  a cross-tier `--reference` is rejected because the dataset digests differ). safety01 captured nothing: both failing
  repeats are ERROR with unverified receipts and no validated demonstration in that run. `test -q -W error
  tests/unit/evaluation` 52 passed; the committed-kernel-case replay guard passes with the 5 cases; `dataset validate`
  on both new manifests valid. Diagnosis of the shared `execution_error` signature (case01 r0, safety01 r0/r1, tier0
  ruby r2; stored evidence only): control PROPERTY_HELD with coverage and exit 0; adversarial `RoleOutcome.ERROR`,
  `target_executed=false`, empty coverage, native and docker exit 1, cleanup confirmed, sandbox wall/cpu/host seconds
  equal to passing repeats. So the exploit payload raises before reaching the bound target line; the driver reports
  junit ERROR, `steps/verification.py` maps it to `RoleOutcome.ERROR`, and `policies/verdicts.py:decide` (lines
  118-121) short-circuits any role ERROR to `ExecutionStatus.ERROR`, ending the session as an operational fault. The
  erroring payload identities never succeed and one (cdede16…) recurs in case01 r0 and safety01 r0, so the fault is
  deterministic per payload shape, not flaky. Under the existing rules (`contracts/evidence.py:14-18`,
  `verdicts.py:_roles_are_executable`) a not-executed target is non-valid evidence, i.e. INVALID → INCONCLUSIVE with a
  further round, not ERROR. Wave-2 candidate h4 (drivers report INVALID for an exploit-side exception that never
  reaches the target; ERROR stays reserved for harness/infra faults; evidence-policy change, new identity, owner
  review before merge). Other candidates: h5 auditor instruction/packet trimming (efficiency; `agents/auditor/`), h6
  cmdi-a abstention via outcome-blind producer metadata (sequenced after wave-1 producer work).
- 2026-10-27 Tier2 intake survey (read-only): 126 un-manifested chain directories; all 126 sources resolve once the
  legacy `benchmarks/corpus/` prefix is mapped to `evals/datasets/corpus/`. Only python `xxe-a`/`xxe-b` are
  holdout-eligible today; 12 other rows fit an existing kind but share a family or source tree with tier0/tier1 (they
  belong in tier1, which changes its digest and needs a new reference); 14 rows are operational (`UNABLE_TO_RUN` in
  lite's matrix, to be re-checked natively); 95 need a new recipe kind (no new kind without a human-authored rubric);
  3 are out of boundary. Legacy `oracle.json` fields (`expected_rule` R0/R4/R5/R6, lite tree digests) do not map
  mechanically onto `Oracle`; every oracle needs owner review. Proposed tooling (not built): `corsair dataset draft
  CHAIN_DIR… --recipe-template --split held_out --out .work/intake/<wave>/` producing request.json, a proposed oracle,
  a `corsair.dataset-draft/1` file no loader accepts, and a code-owned review sheet; `corsair dataset freeze DRAFT
  --review review.md --into evals/datasets/gym-tier2.json` refusing on missing decisions, oracle check failures,
  cross-split families, source-stem overlap with tier0/tier1 or more than 64 entries, exiting 1 after writing with
  old and new identities. Gaps found: `families.py` `chain_pair` misses the `/v3/` and `-v3` layouts and compares
  family ids as plain strings (`xxe` vs a later `ih-java-xxe`); family ids are inconsistent across manifests. Wave
  order proposed: python xxe pair → operational rows natively re-checked → sibling rows into tier1 → reviewed python
  recipe adaptations (each a new identity) → one language per wave once its kind has a rubric. Open owner items:
  Perl licence (PLAN-0001/0002), NOASSERTION corpus trees (point in place, copy nothing), rubrics for new kinds.
- 2026-10-27 Wave-1 side-streams merged on `gym/loop` (all offline or scripted; no live tiers): s2 ledger rows without
  scorecards, per-tier gate outcomes, `VerifyRecord` contract (7e150a09 → 672f9cf); s3 family stems, `/v3` pair
  layouts and source-tree overlap in the split check (b27b8d0b → 46fcaa6a; `just dataset-families` on all 20
  manifests and on the tier pair: 0 violations); s1 shared run store `<main checkout>/.runs/gym/{store,runs,reference,
  verify}`, `corsair gym runs`, `corsair gym verify` (tier0 → gate → tier1 → gate → `VERDICT:` line, exit 0/1/2,
  `verdict.json`), `run.json` and `budgets.json` per run, `score_batch` deduplicated into `evaluation/scoring.py`
  (74910d17 → ce197d5a); reconciliation so `verify` writes the canonical `VerifyRecord` that `ledger append
  --verdict` reads (a73a8ebc; a verdict.json of the pre-reconciliation shape is not read; none existed); s4 reviewed
  intake `corsair dataset draft|freeze` (875db9d9 → c88ec3f6; the python xxe pair drafted and frozen in scratch only;
  frozen requests would live in `evals/datasets/corpus/` beside the Perl row; oracles need owner review). Gates on
  `gym/loop` at c88ec3f6: `just check` exit 0; `just -- test -q -W error` 1287 passed, 111 deselected; at a73a8ebc
  `CORSAIR_TEST_TEMPORAL=1 just -- test-docker -q -W error` 61 passed, 1 skipped (long probe). The three existing
  runs and the reference scorecards were copied (no-clobber) into the shared store `/home/al/git/corsair/.runs/gym/`.
  The s2 test pinning the recorded ledger's row ids was loosened to parse-and-byte-identical-render (3a854c52).
  Protocol change: experimenters now run `just -- gym-verify <reference>`; the skill's step 3 says so.
- 2026-10-27 h2 (efficiency, `gym/h2-producer-decisiveness` a41fed02; new producer capability identity, prompt digest
  29624ad8 → cd7f1df2; scorecard identity digests did not change because prompts and skills are outside
  `Settings.identity`: gap recorded for s6). Diagnosis: most producer episodes spent one extra model call on a
  `set_model_response` validation retry (a top-level `reason` that `ProducerDecision` rejects); reference tier0 had 16
  retries in 18 episodes, tier1 36 in 45. Change: one decision-shape sentence in `system.md` plus kind-neutral stop
  criteria in the source-grounding skill (+283 B). `eval-agent producer-expanded --repeats 1`: 2/3 → 3/3, llm_calls
  5 → 3, effective tokens 39,465 → 24,964. tier0 #1 (57ba4e99) REJECTED on ruby aim misses; tier0 #2 (a41fed02)
  ACCEPTED: J 1.455 → 1.553, tokens 37,512 → 23,999, p50 76.2 → 64.8 s, retries 16 → 1. tier1 REJECTED: J 1.403 →
  0.363, java 1.0 → 0.0 and perl 1.0 → 0.0 on `evidence_not_run` + `execution_error` "activity Heartbeat timeout"
  while h1's runs overlapped the endpoint (a sliced java+perl re-run passed 6/6, INCOMPARABLE by design); python 0.8
  → 0.7 with `provider_max_tokens` 2 → 6 (the h1 failure mode); tokens −21.5 %, thought tokens flat (saving comes
  from fewer calls). Decision: inconclusive; clean tier1 re-run after h1 finishes, then either accept or split the
  decision-shape sentence into its own experiment. Lessons: live tier runs must not overlap (s5: run lock in the
  shared store); operational stops must be visible on the scorecard and the gate (s6).
- 2026-10-27 h1 (accuracy, `gym/h1-reasoning-cap` 55c70eae; `ModelSettings.extra_body` admits
  `thinking_token_budget`, new configuration identity). Endpoint probe: `reasoning_effort`, `reasoning.max_tokens`
  and `thinking.budget_tokens` are ignored by the vLLM route; `thinking_token_budget` is honoured (256 → 255
  reasoning tokens then STOP; works through ADK LiteLlm with a tool declared). tier0 at 8192 REJECTED (J −0.114 from
  java r2 `execution_error`; budget engaged once); tier0 at 4096 REJECTED (J −0.014 from javascript r0
  `clean_negative_unqualified`; budget not engaged); no language regressed in either. Sliced case02/adversarial01/02
  ×3 (INCOMPARABLE): `provider_max_tokens` 2 → 0 at both budgets; at 8192 budget-length calls took 155–190 s on the
  contended endpoint and produced 3 `episode_timeout`; at 4096 no timeouts, 4 `execution_error` evidence-side stops,
  5/9 verified vs 7/9 reference. tier1 not run. `eval-agent producer-expanded` 2/3 both before and after. Decision:
  inconclusive; a non-overlapping tier1 at 4096 is the decisive run. Protocol flaw found: tier0 is at 1.0 verified in
  every language, so its objective margin is noise; the smoke gate must stop a candidate only on a language
  regression or a token-ratio breach (folded into s6), and accuracy hypotheses whose target cases exist only in tier1
  are gated on tier1.
- 2026-10-27 s6 merged (a4ac5cca, 88245217): `RunIdentity` (config, prompt, spec, output-schema, skills, budget
  digests, image and model ids) on trajectories and scorecards with an "Identity changes" line on the gate;
  operational-stop rule in `scoring.operational_stop` (role ERROR always behavioural; heartbeat/activity timeouts,
  cancellation, lost host, `evidence_not_run` with an execution stop are operational); per-language
  `operational_episodes` and `verified_accuracy_without_operational_failures`; gate reason
  `operationally_confounded` (keeps REJECTED); smoke gate mode (`gate(..., smoke=True)`, `corsair gym gate --smoke`).
  Re-scores of the reference tier0/tier1 and h2's tier1 reproduce every existing field; h2 tier1 shows java 3 and
  perl 1 heartbeat-timeout episodes (confounded), python a real regression. s5 merged (2ecb7288, 885d0a79):
  `<gym root>/lock/holder.json` taken by `gym run` and `gym verify` (held across both tiers), `flock`-guarded
  publish, stale-pid reclaim, bounded wait (`--lock-timeout`, default 2 h, exit 2), `gym lock status|release
  --force`, wait recorded in `run.json`; scripted Temporal integration test shows a second run waits. `verify` now
  gates tier0 in smoke mode (222e5893). Gates on `gym/loop` at 222e5893: `just check` exit 0; `just -- test -q -W
  error` 1342 passed, 113 deselected. Not yet run on this HEAD: `just test-docker` (deferred until the live decisive
  runs for h1 and h2 end, so sandbox load does not skew their timing).
- 2026-10-27 Decisive tier1 runs, serialised, no overlap, gated against `ref-w1-tier1` (same dataset, budgets,
  images). h1 at `thinking_token_budget` 4096 (identity 483d950c; run `gym-tier1-20261027t032630-712b10`, 34 min
  26 s): REJECTED on `objective_below_threshold` only (ΔJ −0.176, token ratio 1.070, no language regressed);
  `provider_max_tokens` 2 → 0, calls at the 12,288 cap 2 → 1, python verified 0.8 → 0.9, macro verified 0.967 →
  0.983; J fell because 5 `execution_error` episodes (trusted probe ERROR after audit ACCEPT; safety01 r1,
  adversarial02 r0, ruby r1, java r1, c r0) score −0.5 each against 3 in the reference. h2 clean (identity
  34f22f5e; run `gym-tier1-20261027t040114-47b765`, 39 min 5 s): REJECTED on `language_regressed` (python 0.8 →
  0.6) and the objective (ΔJ −0.222), token ratio 0.956; java and perl recovered fully from the overlapped run
  (heartbeat timeouts 4 → 0), so the earlier confound was real and the python regression is behavioural
  (`provider_max_tokens` 4, probe ERROR 5, one `audit_reject` R4 on cmdi-a r0). Lessons: the reward's −0.5 for
  ERROR plus the kernel's ERROR classification of a payload that raises before the target make J hostage to
  3–6 such episodes per tier1; h4 is the prerequisite for measuring h1 again; h2's stop-criteria text is dropped
  and its decision-shape sentence becomes h2a. Observation to check: c-intoverflow-a r0 in the h1 run hit the
  output cap but was recorded as `execution_error`, not `provider_max_tokens`. Run directories of h1/h2 copied into
  the shared store. Ledger rows `h1-tier1`, `h2-tier1` (rejected).
- 2026-10-27 Docker suite on `gym/loop` at 0b1b600f: `CORSAIR_TEST_TEMPORAL=1 just -- test-docker -q -W error`
  61 passed, 1 skipped (long probe). h4 (wave 2, not implemented, no commit): read-only analysis of the 27
  adversarial-ERROR raw receipts in the shared store corrects the earlier diagnosis. The bound finding line IS
  covered in 19 of the 20 mappable receipts (reference 3/3, h1 run 3 of 3 with a role-ERROR adversarial, h2 clean
  6/6); the "target not executed, empty coverage" picture came from `steps/verification.py:_error()` discarding the
  receipt's `covered_lines` and setting `target_executed=False` for `observation_kind=execution_error`, and from
  drivers setting `target_executed` only for held/invalid/violation kinds. So the briefed rule (INVALID only when the
  target did not execute) matches 0 observed episodes and would not move J. The rule that would affect them (status
  ERROR with `observation_kind=execution_error`, bound line covered, control HELD, cleanup confirmed, no harness
  fault → INVALID with an explicit reason) reclassifies a target-side exception outside the recipe's
  `allowed_exceptions`, which AGENTS.md keeps explicit; it is an owner ruling, not an experiment. Two genuine faults
  remain ERROR correctly: c-intoverflow-a r0 in the h1 run (`SandboxExecutionError`, no driver record) and the java
  control-role ERROR. Separate correctness defect, also for the owner: `_error()` discards coverage so stored ERROR
  observations misreport execution; fixing it changes rebuilt observations and so saved-evidence re-validation of
  old ERROR results. Ledger row `h4` (rejected: premise false).
- 2026-10-27 h2a (wave 2, efficiency, `gym/h2a-decision-shape` 873a8c56; producer prompt digest 29624ad8 →
  cd7f1df2, +181 B): `just -- gym-verify` (verdict `verify-20261027t044743-f332ad`): tier0 smoke ACCEPTED
  (J −0.111 reported only; tokens 0.974×; p50 76.2 → 58.1 s), tier1 REJECTED (`language_regressed` python 0.8 →
  0.6 and ruby 1.0 → 0.0; J −0.600; tokens 0.985×; no operational confound). Response-validation retries fell 16 →
  4 (tier0) and 41 → 17 (tier1), model calls per episode 4.69 → 4.38, but the token saving is 1.5–2.6 %, under the
  10 % bar. Stops: tier1 `execution_error` 3 → 6, `provider_max_tokens` 2 → 5. Worktree gates: `just test` 1343
  passed, `just check` exit 0, wheel resources load outside the checkout. Ledger row `h2a` (rejected). Instrument
  notes: `verify` prints JSON only when piped (no `VERDICT:` text line); the reference scorecards predate
  `run_identity`, so the gate's identity line reads unknown until the reference is re-scored.
- 2026-10-27 Reference scorecards re-scored with the s6 scorer (`corsair gym score … --budgets
  evals/experiments/budgets.json`): every metric and per-language value identical to `ref-w1-tier0/tier1`; the new
  `run_identity` and operational fields populated (0 operational episodes); the original run block (0697ff08) kept
  because `score` on an imported run directory without `run.json` stamps an empty run context (dx nit, s7);
  originals saved as `reference/*.pre-s6.json`. Self-gate of tier1 now prints "Identity changes: none.".
  Wave-2 state: h4 premise false (owner ruling pending on target-side exceptions), h2a rejected; the next
  behavioural experiments wait on the owner's two rulings (evidence policy for target-side exceptions; the
  verifier's coverage discard on ERROR), because J is dominated by those episodes in every run so far.
- 2026-10-27 s7 merged (6c4228b8, 890616e9): `verify` writes its `VERDICT:` line to stderr in every format;
  `score` takes the run context from `run.json`, else the scorecard beside the report, else `--run-id`/
  `--git-commit`/`--git-branch`, else warns; recovers `run.json` for imported runs; `gym run` stores the run block in
  `run.json`. Gates on `gym/loop` at 6c4228b8: `just check` exit 0; `just -- test -q -W error` 1345 passed, 113
  deselected; `CORSAIR_TEST_TEMPORAL=1 just -- test-docker -q -W error` 61 passed, 1 skipped.
- 2026-10-27 Delivery gate on `gym/loop` at 8deb2e21: `just build` exit 0 (`corsair-0.1.0-py3-none-any.whl`);
  installed with the providers extra into a fresh venv outside the checkout; `python -I` loads the producer
  instruction (2,131 B) and the gym modules from the wheel; the wheel contains no `.runs`, `.state`, `.work` or
  ledger content. 54 commits ahead of `main`, nothing pushed. Blocked on the owner's rulings (target-side
  exception policy; coverage discard on ERROR observations; publication of `gym/loop`; xxe oracle review).
- 2026-10-27 Owner rulings ("Go" on the orchestrator's recommendations 1 and 2): (1) the kernel keeps a target-side
  exception explicit as ERROR; the gym scores such an episode 0 under a new `target_exception` gate reason instead
  of −0.5, derived from the raw receipt (s8); a blind-retry workflow policy after a target-side exception is deferred
  to a reviewed spec of its own. (2) ERROR observations keep receipt coverage and carry an explicit error kind (w2),
  verdict-neutral, with re-validation tolerant of results stored before the change. Publication of `gym/loop` and
  the xxe oracle freeze remain pending explicit instruction. Next: re-score the reference under the new reward (same
  runs), then re-measure h1 at budget 4096 against it.
- 2026-10-27 s8 merged (7ab72351, b97a592e): gym reward 0 for a target-side exception episode (`target_exception`
  stop, derived from the raw receipt: driver record with `observation_kind=execution_error`, cleanup confirmed, bound
  line covered, no error); reference re-scored in place under this reward (tier0 J 1.4554 → 1.4832 with 1 such
  episode; tier1 1.4025 → 1.4108 with 3; previous copies `*.pre-s8.json`; ledger rows `ref-w2-tier0/tier1`). h1's
  decisive run re-scored: J 1.2261 → 1.2594 (3 of 5 ERROR episodes reclassified; c r0 `SandboxExecutionError` and
  java r1 control ERROR stay −0.5); against the re-scored reference still REJECTED on the J margin only (ΔJ −0.151,
  verified 0.967 → 0.983, worst 0.8 → 0.9, tokens 1.070, no regression): with one case per non-Python language a
  single ERROR episode costs ≈0.085 J, so track-specific criteria follow (s9). w2 merged (4593c936, 008fdc0c): ERROR
  observations keep receipt coverage, `target_executed` derived in the verifier, `RoleObservation.error_kind`
  (target_exception / harness / sandbox); no driver, image or identity change; re-validation unchanged for old results
  (ERROR roles were never admissible); 425 stored rounds show 0 verdict differences. Gates on `gym/loop` at 4593c936:
  see the next bullet.
- 2026-10-27 Gates on `gym/loop` at 4593c936 (after s8 and w2): `just check` exit 0; `just -- test -q -W error`
  1387 passed, 113 deselected, 0 warnings. Docker suite deferred until the h1 re-measurement's live run ends.
- 2026-10-27 s9 merged (471a9bd1; `justfile` pass-through c662c9dc): gate tracks `objective` (unchanged default),
  `accuracy` (no language regression, tokens ≤ 1.10×, macro verified accuracy up by at least one majority flip in the
  largest language, 1/60 on tier1, or the `--target-language` up by one of its cases) and `efficiency` (no regression,
  macro verified accuracy ≥ baseline, macro effective tokens or comparable macro p50 seconds ≤ 0.90×; latency counts
  only at equal concurrency with 0 operational episodes); `sandbox_fault` operational reason for a role ERROR with no
  driver record. On real data: h1's decisive run ACCEPTED under `accuracy` and REJECTED under `objective`; h2's
  clean run REJECTED under `efficiency`; reference vs itself REJECTED under each track; c-intoverflow-a r0 in the
  h1 run becomes operational (`sandbox_fault`) with no reward change. Gates on `gym/loop` at c662c9dc: `just check`
  exit 0; `just -- test -q -W error` 1424 passed, 113 deselected.
- 2026-10-27 h1 re-measurement (`gym/h1-rerun` f98323ca = h1 + gym/loop, budget 4096, s8 reward, verify
  `verify-20261027t102336-60e6a5`): tier0 smoke ACCEPTED (J +0.083, tokens 0.900×, all languages 1.0); tier1
  REJECTED (`language_regressed` ruby 1.0 → 0.0 via 2 `target_exception` episodes, `objective_below_threshold` ΔJ
  −0.570, `tokens_above_ceiling` 1.210×; macro verified 0.967 → 0.817; p50 +28 s with javascript 64 → 159 s; cap
  stops 2 → 0 and python 0.8 → 0.9 as before; 0 operational episodes). Compared with h1's first decisive run of the
  same configuration (tokens 1.070×, ruby 1.0, J 1.259): the two runs differ more than any candidate effect
  measured so far, so the corpus (one case per non-Python language) and run-to-run variance, not the gate, are
  the limiting factor. h1 closed as rejected; ledger row `h1-rerun`. Next: a second reference run of the same
  configuration to measure the noise floor, then corpus growth (sibling rows into tier1 via reviewed intake).
- 2026-10-27 Docker suite on `gym/loop` at cb4c829a (after w2, s8, s9): `CORSAIR_TEST_TEMPORAL=1 just -- test-docker
  -q -W error` 61 passed, 1 skipped (long probe). Noise-floor run started: a second tier1 at the reference
  configuration (identity 34f22f5e, no extra_body) to be compared case by case with `ref-w2-tier1`.
- 2026-10-27 Noise floor (`gym-tier1-20261027t111450-29968e`, reference configuration, identity 34f22f5e, same
  images, budgets and dataset, 40 min 6 s, 0 operational episodes) vs `ref-w2-tier1`: J 1.411 → 0.860, macro
  verified 0.967 → 0.800 (ruby 1.0 → 0.0 on 2 `target_exception` episodes), macro tokens 1.115×, p50 1.152×;
  per-language token deltas −18 % to +86 %. Majority flips 3 of 15 (case02 lost on `provider_max_tokens`, ruby lost
  on `target_exception`, safety01 gained), every flip on one of those two stops; six cases identical across four
  runs. Bootstrapped 95 % band for two identical runs at 3 repeats: J ±0.54, macro verified ±0.20, python verified
  ±0.30, token ratio 0.79–1.26; probability that identical configurations trip the gate: J ≥ +0.01 0.47, tokens
  > 1.10× 0.21, some language regressed 0.48. At equal cost, 3× cases per language narrows the J band to ≈0.30
  versus ≈0.49 for 9 repeats; the five single-case languages amplify J through the worst-language term. All three
  gate tracks REJECTED the identical configuration. Ledger row `ref-w2b-tier1`. Consequences: (a) treat tier1
  3-repeat differences inside the band as noise; (b) the gate needs a repeat-aware criterion (delta outside the
  measured band, or a confirmation run) before any behavioural acceptance; (c) corpus growth is the next lever:
  12 sibling rows into tier1 and the xxe pair, through `dataset draft` and owner-reviewed oracles.
- 2026-10-27 Wave-3 intake draft (private, `.work/intake/wave3/`, nothing frozen, no oracle decided): 12 rows
  drafted with `corsair dataset draft`; 10 sibling rows fit existing kinds and belong in tier1 (8 under split
  `chain`, perl's 2 under `dev`, matching their anchors; drafted as `held_out` they are refused by pair, source-tree
  or family-stem overlap) and the python xxe pair is holdout-eligible (no overlap in any split). Review sheets per
  group plus `review-index.md`; freeze on every unreviewed sheet exits 2 `decision_missing` without writing. Owner
  notes: 5 rows (java xxe-a, javascript prototypepollution-b, perl xss-a, ruby pathtraversal-a, c intoverflow-b)
  carry legacy negative or unsupported labels their kinds cannot express (not in `CLEAN_NEGATIVE_QUALIFIED_KINDS`),
  so they need amend or reject; 4 rows share a snapshot digest with a frozen tier tree (perl xss-a/b, java xxe-a, c
  intoverflow-b) and are likely duplicates. Templates per kind under `.work/intake/wave3/templates/` with operator
  notes in `.note.json` sidecars (the template loader refuses unknown fields). Tooling gaps found (s10): freeze
  builds drafted members without family stem or trees, so `family_stem_crosses_splits` never fires for them; draft
  takes the language from a `common/` directory for C rows; freeze's tree keys do not skip the `v3/` layout. The
  survey's "12 sibling rows" resolved to 10; python pathtraversal-a/b need an unbuilt recipe adaptation.
- 2026-10-27 s10 merged (c0f7db79, be756d04): freeze builds drafted rows with `families.request_member` (same
  stems and trees as frozen entries), draft derives the language from the recipe kind (`families.kind_language`),
  freeze's own tree rule removed in favour of the shared `variant_stem` check (an unreadable or changed `--against`
  request is refused as `against_unreadable`). On the wave-3 drafts freeze and `just dataset-families` now agree for
  every row and split; the C group re-drafted as `sib-c-integer-overflow-v2/` (`ih-c-intoverflow-b`). Known gap:
  `family_stem` recognises only `ih-`/`chain-` prefixes, so `syn-` families match by pair and tree only. Gates on
  `gym/loop` at c0f7db79: `just check` exit 0; `just -- test -q -W error` 1432 passed, 113 deselected. The loop
  now waits on the owner: review decisions for the 12 drafted rows, the noise-aware gate ruling, and publication.
