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
