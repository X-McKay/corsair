# PLAN-0002: improvement loop, rounds 1 and 2 (2026-10-25 to 2026-10-26)

Two rounds of parallel experiments on `feature/improvement-loop`, cut from `main` at `d3e69c00`. Each experiment ran as one
Opus agent in its own worktree and branch (`exp/<name>`, `exp2/<name>`), reported hypothesis, changes, evidence, checks,
risks and a recommendation, and was merged, held or discarded by the orchestrator against the kernel rules in
[AGENTS.md](../../../AGENTS.md). This record keeps the decisions, the live diagnostics that were run at integration, the
gates that ran, and the items that need the project owner. Live numbers are small-n diagnostics on the operator's local
model (`Qwen3.6-35B-A3B-NVFP4` via `hosted_vllm/`), not promoted baselines; see the [baseline policy](../../../evals/baselines/README.md).

## Round 1 (20 experiments)

| Experiment | Agent recommendation | Decision | Notes |
| --- | --- | --- | --- |
| latency-parallel-roles | discard | DISCARD | No code. Concurrent roles would violate the control-cleanup-before-adversarial gate (policies/risk.md:21, extensions.md:46, test_evidence guard). Measured: evidence step 1.15 s -> 0.65 s if allowed; container run time dominates (~0.5 s/role). Operator decision needed to revisit. |
| accuracy-control-feedback | merge with caveats | MERGED | ADR 0005 (proposed) + signature guard test; no behaviour change. Finding: control-side retry feedback leaks the exploit outcome by elimination. |
| dx-offline-cli-tests | merge | MERGED | +27 offline tests (0.4 s), cli.py coverage 60%->80%, mutation-checked. Reported CLI nits: rescore --output default dead fallback; exit 2 shared by usage and runtime errors. |
| cli-report-compare | merge with caveats | MERGED | Per-case report table + `corsair compare` (regression exit 1, dataset digest guard). Caveat: `report --format json` now emits the full report, not summary only (offline test updated). |
| cli-result-rendering | merge with caveats | MERGED | Verdict-led result panel, rounds table, observation role table; JSON byte-identical; payload/reasoning never shown (tested). terminal.py conflict with compare resolved by hand. |
| cli-runs-explorer | merge with caveats | MERGED | `corsair runs` (newest first, --case/--limit) and `inspect --evidence` (allowlisted receipt fields); read-only store enumeration; 500 runs list in ~55 ms. |
| dx-tooling-guards | merge | MERGED | `just toolchain` check (versions + remedies), test_justfile skips with remedy on unpinned just, LiteLlm test no longer needs the extra (fixes the pre-existing failure), models.py ImportError remedy, setup.md table. Found: Nix vs non-Nix venv recreation drops extras; Nix-built venv fails outside Nix (libstdc++). |
| dx-error-messages | merge | MERGED | failure_remedy mapping (10/10 scenarios now carry a fixed remedy line; messages and exit codes unchanged); doctor failed checks carry remedy. Incident: agent submitted 2 workflows to what it thought was a down Temporal on 7233 (it was the k3s-forwarded cluster Temporal); cancelled/terminated, no activities ran. |
| dx-local-stack | merge | MERGED | `just settings-init / temporal-up / temporal-down / worker-up / worker-down / demo`; demo ran on this rig in 3.1 s. Finding: localhost:7233 is NAT-forwarded by k3s to a cluster Temporal (prod namespaces); port check now treats "something answers" as busy. |
| accuracy-max-tokens | merge with caveats | MERGED (code commit 450175a8 only) | New operational gate `provider_max_tokens` on both ADK routes (LiteLLM `length`, native finish_reason); AuditInput cap defaults to Budget default 12288. Held back b87507d2 (frozen auditor fixtures 2048->12288) pending a live auditor rerun. |
| accuracy-auditor-packet | merge with caveats | MERGED | Rubric ids R1-R4/ALL, sectioned packet with fenced numbered excerpt, no reload invitation, audit_rule in eval rows. Agent-behaviour change: new prompt/skill digests; live auditor eval unrun. |
| latency-producer-prompt | merge with caveats | MERGED | Instruction 3711->3388 B (-2.7%/call), no-reload guidance, measurement script + size-pinning tests. Finding: ADK SkillToolset adds ~3.1 KB (26%) per call for a preloaded skill; dropping it is a capability-identity decision for the owner. |
| simplify-adk-adapter | merge with caveats | MERGED | Shared stop ladder `_completed_text`; 577->568 LOC; 20 traced cases byte-identical. The 100+ LOC hypothesis did not hold. |
| latency-evidence-profile | merge | MERGED (image rebuild pending) | Host-side costs <25 ms; container coverage tracing dominates. Driver sets COVERAGE_CORE=sysmon: per-role wait 1028->700 ms (-32%), evidence -27%, identical observations. Needs `just images` + docker suite on rebuilt image. Also: CLI imports ~530 ms (temporalio via logging.py). |
| simplify-verification-step | merge with caveats | MERGED | One receipt identity/cleanup validator (`_cleaned_raw`), shared bundle check; 515->509 LOC; strings byte-identical; docker suite passed. Finding: docker tests use fixed operation ids and collide across parallel worktrees on one daemon. |
| cli-live-progress | merge with caveats | MERGED | Live rich panel (phase, session/round n/max, last gate, deadline, timeline) for investigate --wait / inspect --watch / eval; status queries gained bounded fields; replay tests pass. 3 keep-both conflicts resolved. |
| accuracy-target-binding | merge | MERGED | Pure ast check (file/line/function/async/payload_parameter/fixed_kwargs/required params) run in prepare -> PREPARE_BLOCKED -> UNABLE_TO_RUN before any model call; +2 ms; 0 false blocks on 10 corpus snapshots; 5 malformed variants now blocked pre-model. |
| latency-cli-startup | merge | MERGED | Lazy handler imports, temporalio interceptor moved to observability/lifecycle.py, Docker SDK no longer loaded by report/compare: --version/--help 629->39 ms, report/compare 621->120 ms; import-guard tests added. |
| accuracy-max-tokens (fixture commit b87507d2) | merge with live rerun | MERGED after live rerun | auditor-dev live: prompt change alone 5/6 (0 operational); with cap 12288: 6/6 pass, 0 operational, 6701 output tokens. Baseline 2026-10-26 was 3/6 with 2 MAX_TOKENS stops. |

## Live diagnostics run during integration (operator vLLM, Qwen3.6-35B-A3B-NVFP4, hosted_vllm/ route)

- auditor-dev before (2026-10-26 candidate): 3/6 pass, 2 operational (MAX_TOKENS), 10 llm calls, 9549 out tokens, 106 s.
- auditor-dev on integrated tree (prompt/packet changes, fixtures still 2048 cap): 5/6, 0 operational, 7 calls, 6367 out tokens, 62 s; 1 malformed AuditResult.
- auditor-dev with fixture cap 12288 (b87507d2 cherry-picked): 6/6, 0 operational, 10 calls, 6701 out tokens.
- producer-dev before: 0/3 (budget 3 calls exhausted). producer-dev on integrated tree (pre producer-packet): 0/3, each episode 12 llm calls / 12-13 tool calls, 70-110 s, 'exhausted its LLM-call budget'.
- Traced episode: list_files + read_file, decision ready at 15 s, then 10x `set_model_response` rejected. Root cause: ProducerDecision is a pydantic RootModel, so ADK's set_model_response declaration has one required param `root: anyOf[$ref ProducerProposal, $ref NoGroundedCandidate]` (no top-level object fields); the vLLM tool-call path passes `root` as a JSON string and validation fails every time. Fix for round 2: flat discriminated output object (contract/schema-digest change), then re-run producer-dev.

## Round 2 (35 experiments: 20 general, 6 per language, 9 evaluation and iteration depth)

| Experiment | Agent recommendation | Decision | Notes |
| --- | --- | --- | --- |
| docker-test-isolation | merge | MERGED | Session-prefixed operation ids + teardown sweep of own containers only; 7 cross-run failures before, 0 in 2x/3x concurrent runs after; test-only. |
| report-markdown | merge with caveats | MERGED | `--format markdown` for report/compare with identity + baseline-policy caveats; JSON byte-identical; reasons (model text) replaced by code-chosen stop gates. |
| prepare-snapshot-profile | merge | MERGED | iter_snapshot_files/read_source fetched+hashed the whole blob once per tar member (O(files x size)); now once per call. list_files x20: 69.7 s -> 0.57 s on 991 files; Docker materialization same saving; all admission rules unchanged; security/docker/temporal suites pass. |
| ledger-agent-rows | merge | MERGED | agent_row_ledger + row_ledger; agent summaries now carry gate_ledger/failure_stops; compare gains gate_delta and per-case stops (e.g. live baselines: producer_invalid:llm_budget 3/9, provider_permanent 2). |
| auditor-no-toolset | merge with caveats | MERGED (live rerun pending) | Auditor has no tools (matches docs): request 7683->3481 B (-55%), no set_model_response path, llm_call_limit 2->1; identity digests change. |
| live-eval-recipes | merge with caveats | MERGED | `just live-agent ROLE DATASET [BASELINE]` / `live-chain`: refuses without settings/provider env, writes .runs/live/<stamp>/ with report, identity.json, comparison, README draft. Finding: committed 2026-10-26 baselines no longer match current dataset digests. |
| eval-concurrency | merge with caveats | MERGED | Settings max_concurrent_activities (default 4) / max_concurrent_workflow_tasks; measured 8-case scripted batch: concurrency 8 at 4 slots 12.5 s, at 8 slots 6.3 s (7.8x); no evidence starvation; config_digest changes. |
| simplify-workflow-rounds | merge with caveats | PENDING (merge last) | run(): 275->92 lines, nesting 9->6; file +74 lines; 31/31 recorded histories replay; will conflict with timeouts/timeline branches. |
| producer-no-skilltoolset | merge with caveats | PENDING (rebase requested) | -3283 B/call (-28%), removes ADK load_skill contradiction; 10-file conflict with auditor-no-toolset; agent asked to rebase onto integrated head. |
| simplify-terminal | merge only if first, else discard | DISCARD | Byte-identical (344 renders) but 915->916 LOC; structural only; would conflict with the already-merged markdown export and the pending inspect-ledger / eval-live-table branches. |
| evals-adversarial-depth | n/a | BLOCKED | Agent stopped by a safety classifier before writing anything (hostile-target fixtures: tracing tampering, forged records, secret-in-exception, etc.). No changes. Needs the owner to decide how this defensive regression suite is authored. |

### Round-2 live checks (operator vLLM)
- auditor-dev via `just live-agent` on the tool-less auditor vs cap-12288 baseline: 6/6 pass (unchanged), tool_calls 6->0, llm_calls 10->6, input tokens 26638->6516 (-75%), output tokens 6701->9346 (+39%), agent seconds 69->84 (+15 s), no regression. Record: .runs/live/20261026T041453Z-agent-auditor-auditor-dev (README draft generated by the recipe).
| scanner-line-binding | merge with caveats | MERGED | derive_target_line(): line-less findings bind to the first executable body statement (never the def line, which runs at import); line_provenance recorded in PreparedCase/AuditInput/packets/inspect --evidence; +38 tests; Temporal/docker pass. |
| doctor-model-check | merge with caveats | MERGED | `doctor --model`: config/credential-name/producer/auditor/tool-round-trip probes through the real ADK model object, 32/128-token caps, redaction tested, LiteLLM stdout banner redirected; default doctor still model-free. |
| venv-drift | merge | MERGED | .python-version=3.12, flake UV_PYTHON -> UV_PYTHON_PREFERENCE=system, native-library (libstdc++) FAIL before collection, just sync pre-check; one .venv passes in and out of Nix (449/444). macOS CI unverified. |
| producer-output-schema | merge | MERGED | ProducerDecision is a flat Contract (kind/submission/reason) so set_model_response has typed top-level params; old RootModel declaration could never be satisfied (union_tag_not_found); stored histories decode; output_schema_digest changes. Live producer-dev rerun in progress. |
| dataset-validate | merge | MERGED | `corsair dataset validate` (entry/digests/request/source/target_binding/oracle checks, --fix-digests), 35 ms for all datasets; finding: held_out.json is not a manifest. |
| inspect-ledger | merge with caveats | MERGED | Rounds table "Stopped at" column + case stop from the pure gate ledger (verified against committed receipts offline); InvestigationResult.timeline (<=32 PhaseTransition, additive, replay-safe); Phases table with durations. |
| activity-episode-timeouts | merge with caveats | MERGED | policies/time_bounds.py: request <= episode < activity; producer episode 900->285 s, auditor 300->165 s within unchanged activity windows; a stalled model now ends as typed episode_timeout with counted usage instead of a lost ActivityError; replay unchanged. |
| driver-coverage-api | merge | MERGED (image rebuild pending) | In-process coverage json_report (no second interpreter), pytest autoload off, compileall in image: per-role container 418->284 ms, driver 287->166 ms; 8 frozen records byte-identical; full docker suite passed on scratch tag. |
- producer-dev via `just live-agent` on the flat-schema tree vs pre-change baseline: **3/3 exact_match** (was 0/3), llm_calls 36->10, tool_calls 37->10, output tokens 26280->4925, 15-20 s per episode (was 70-110 s), 3 fail->pass, no regressions. Record: .runs/live/20261026T042200Z-agent-producer-producer-dev. Root cause confirmed: RootModel output schema made set_model_response unsatisfiable.
- `doctor --model` live: model_config/credentials/producer/auditor pass (MAX_TOKENS at the 32-token probe cap, reasoning model), tool probe WARN inconclusive at 128 tokens; 7 s wall.
| eval-live-table | merge with caveats | PENDING | Evaluation query gains started + bounded child rows (state/started/finished, <=64); live per-case table with progress bar; replay fixture added. |
| coverage-line-normalization | merge with caveats | MERGED | policies/line_binding.py: header/docstring/continuation lines bind to the reported statement line (0 of 1464 lines bound to an unreported line); def-line findings now stricter (function must run); PreparedCase.target_line. |
| producer-no-skilltoolset | merge with caveats | MERGED | Producer tools = read_file + list_files only; procedure preloaded; loader accounting removed for both roles; -3283 B/call (-28.8%); capability identity changes; live producer rerun pending. |
| evals-auditor-depth | merge with caveats | MERGED | auditor-rubric.json (audit05-11: R1-R4, INSUFFICIENT_CONTEXT, 2 ACCEPT) with optional expected rule in oracles; rule_mismatch match kind; labels need human review; live rubric run pending. |
| simplify-evaluation | merge | MERGED | Dead DuckDB scorecards.py + SQL removed, duckdb dependency dropped (uv.lock -17 lines), one frozen-file reader; evaluation/ 1835->1704 LOC, repo -635 lines; wheel verified. |
| evals-held-out-families | merge with caveats | MERGED | families.py: cross-manifest family/case/chain-pair split checks (`just dataset-families`), family/split labels on rows, per-family views on report/compare; checked-in datasets disjoint; finding: held_out.json is a legacy listing with no runnable requests, so no evaluable held-out split exists yet. |
| evals-skill-references | merge (trusted-code path) | MERGED | 12 per-class references (6 classes x 2 roles); select_reference() picks at most one by recipe kind + finding keywords and the packet builders append it under "## Class reference"; on-demand loader path dropped (no loaders remain); runtime_skills_digest changes. |
| cli-explain-verdict | merge | MERGED | policies/explanation.py: pure statements (verdict/rule/session/shortfall/policy/fix/change) over result + ledger; `corsair explain RUN_ID` and `inspect --explain`; privacy-tested; chain test on real results. Finding: the result panel Reason row prints result.reason which can be auditor/abstention model text (fix separately). |
| dx-agent-preview | merge | MERGED | evaluation/preview.py + `corsair agent preview ROLE REQUEST` (parts with bytes/tokens/sha, --output/--diff/--full); measurement scripts now thin wrappers, byte-identical output. |
| coverage-line-normalization | merge | MERGED | Reconciled with scanner-derived lines: derivation fills a missing line, binding normalises a declared one; PreparedCase has target_line + line_provenance + bound_line; inspect --evidence shows declared/bound/provenance; merged tree 760 offline / 50 Temporal. |
- Docker suite on rebuilt corsair-python:0.1 (601f395f76b7, new driver): 23 passed, 1 skipped, 2 chain tests failed because the chain test's scripted model json.loads'd the whole packet after the class-reference section was appended; fixed in the test (raw_decode) -> 2 passed.
- producer-dev via `just live-agent` on the final round-2 configuration (flat schema + no SkillToolset + class references) vs flat-schema record: 3/3 exact_match, llm_calls 10->5, tool_calls 10->5, input tokens 35777->16262 (-55%), one episode in a single call; no regression.
| evals-candidate-replay | merge | MERGED | `corsair dataset replay-candidates REPORT DATASET`: mismatching producer proposals replayed through the real verify path; demonstrates/does-not column; never edits oracles; docker test. |
| evals-scanner-intake | merge | MERGED | `corsair intake REPORT --source-root DIR [--recipe-template]` dry run + `just eval-intake` over evals/datasets/intake.json (12 findings, 12/12 agree; 3 admissible, 9 blocked across 8 reasons); conversion in adapters/scm/requests.py; bind_target_line shared with prepare. |
| lang-python | merge with caveats | MERGED (three-way union: secret_disclosure, command_sentinel, javascript, ruby; PYTHON_CALLABLE_RECIPES guards; Settings.images follows a configured image) | PythonCommandSentinel recipe (python.command_sentinel/1), Recipe discriminated union with kind-less default, images map + image_id_for, per-kind driver templates, 3 corpus rows migrated (cmdi-b, codeinjection-b positive; cmdi-a negative) verified on real Docker; corpus-python.md map of ~37 rows; auditor R4 generalised (agent-behaviour change). |
| lang-javascript | merge | MERGED (first language branch; Python-only gates guarded by recipe type) | JavaScriptRecipe javascript.prototype_pollution/1, node:22 image by digest, drivers/javascript/driver.mjs (node:test + V8 coverage), prototypepollution-a-v3 row verified (control held / adversarial violated, cleanup confirmed), 4 docker tests, ~0.16 s per role. |
| lang-ruby | merge | MERGED (re-reconciled onto the JS head; fixtures guard widened to Ruby secret-disclosure) | RubyRecipe ruby.secret_disclosure/1, ruby:3.1 image by digest, drivers/ruby/driver.rb (minitest + Coverage), pathtraversal-b/v3 row verified incl. --fixed blocked, 3 docker tests, ~0.11-0.15 s per role. |
- auditor-dev final configuration (tool-less + class references) vs tool-less record: 6/6, 0 tools, 1 call each, no regression; input tokens 6516->8532 (+2016, the appended class note), output +385.
- auditor-rubric (new cohort, first live contact, 2 repeats): 11/14 exact; R1/R3/R4 rejections 2/2 each with the expected rule; R2 (audit06) 1/2; audit09 (expected INSUFFICIENT_CONTEXT) ACCEPTed 2/2 -> label needs human review; 0 operational failures.
- Docker suite on head 95374609 (Python + JavaScript runtimes, rebuilt images): 30 passed, 1 skipped (long-probe opt-in).
| lang-c | merge with caveats | MERGED (re-reconciled onto head; /work noexec relaxation scoped to c.integer_overflow/1) | CRecipe c.integer_overflow/1; gcc image by digest; drivers/c/driver.py compiles a fixed harness under ASan+UBSan with gcov, a target-bound sanitizer report is the only VIOLATION, crash/compile failure is ERROR; c-intoverflow-a/v3 verified both ways; 5 docker tests; ~0.2 s/role. OWNER DECISION: the C image /work tmpfs drops noexec (NATIVE_EXEC_KINDS), scoped to that kind and documented. |
- After exp2/lang-python merge (head 82d032ef, Python+JavaScript+Ruby runtimes): Temporal 50 passed/10 skipped; images rebuilt (python f3239cc4b3cb, javascript a053c7f4b56b, ruby df5363c39589); Docker suite 37 passed, 1 skipped.
- After exp2/lang-python (auditor R4 generalised, command-sentinel references): producer-dev 2/3 (one candidate_exact_mismatch: exploit "../../private/secret.txt"); `corsair dataset replay-candidates` replayed it through the real kernel: control held, adversarial ERROR, not covered -> genuinely wrong payload (one traversal too deep), not an oracle gap. n=3 so treat as variance until repeated. auditor-dev 6/6, no regression.
| lang-perl | merge | MERGED | PerlRecipe perl.html_injection/1 (markup-count property; secret disclosure fits no Perl row), perl:5.40 image by digest, drivers/perl/driver.pl (Test::More + core-only line tracer), xss/b row verified both ways (request points at the frozen corpus tree in place: licence decision PLAN-0001 item 5 still open), 6 docker tests, ~0.2-0.35 s/role. |
| simplify-workflow-rounds | merge with caveats | MERGED (last) | run() 276 -> 92 lines (file +72); re-applied on the final head; 39/39 recorded histories replay across versions; no test changed. |
| lang-java | merge | MERGED (last language branch; union now has 7 members) | JavaRecipe java.secret_disclosure/1; JDK image by digest with vendored, checksummed JUnit 5 + JaCoCo; drivers/java/driver.sh (javac + fixed JUnit test + JaCoCo XML); xxe-b/v3 row verified (control held / adversarial violated, sink line 13 covered); 4 docker tests; ~1.1 s/role (JVM); host confirmed x86_64. |
- Gates on head 97c58027 (Perl + workflow refactor in): check ok; offline 933 passed; Temporal 50 passed/10 skipped; 5 images rebuilt; Docker suite 48 passed, 1 skipped.

- Final head `8f8e18d9` (all six runtimes): `just check` ok; offline 934 passed; Temporal 50 passed, 10 skipped; six images rebuilt (python f3239cc4b3cb, javascript a053c7f4b56b, ruby df5363c39589, java ebe72067568f, perl 771c387f23fc, c 6d80bc5b3631); Docker suite 52 passed, 1 skipped (long-probe opt-in).

## Gates on the integrated branch

Run through the Nix shell on this Linux amd64 host after every merge (`just check`, `just -- test -q`); the Temporal and
Docker suites after any workflow, step, driver or image change. The final numbers are in the last line of the round-2
notes above. The live chain (`just live-chain`), macOS arm64, and every non-Python runtime under a live model remain unrun.

## Decisions for the project owner

1. The C runtime image's `/work` tmpfs drops `noexec` for `c.integer_overflow/1` only (`NATIVE_EXEC_KINDS`), so a
   compiled binary can run; every other control is unchanged. Confirm or revert.
2. The adversarial-depth dataset (hostile targets attacking tracing, receipts, exceptions, timeouts, environment) was not
   authored: the agent was stopped by a safety classifier. Decide who writes that regression suite.
3. The auditor-rubric cohort (`audit05` to `audit11`) and the per-language corpus rows are AI-authored candidates; their
   labels need human review before any promotion. `audit09` (expected `INSUFFICIENT_CONTEXT`) was accepted 2/2 live.
4. `held_out.json` is a legacy listing, not a runnable manifest: no evaluable held-out split exists yet.
5. The Perl corpus licence (PLAN-0001 item 5) is still open; the Perl row points at the frozen tree in place.
6. The 2026-10-26 candidate baselines no longer match the current dataset digests; record fresh baselines with
   `just live-agent` / `just live-chain` and compare with `corsair compare`.
7. The human result panel prints `result.reason`, which can carry the auditor's or an abstention's model text; the
   explanation and markdown views avoid it. A small follow-up should drop it from the panel.

## Next round candidates

- Composed live chain on the Python dev set with the new producer schema, then the first live run of each non-Python
  runtime through the producer and auditor (their prompts are still Python-worded).
- A bytes-payload option on `python.command_sentinel/1` to unlock the deserialization rows; `c.stack_overflow/1` for the
  remaining C rows; the framework-dependent rows mapped in the per-language corpus surveys.
- Live `auditor-rubric` repeats to settle the `audit06`/`audit09` labels; producer-dev repeats to separate variance from
  the class-reference change.
