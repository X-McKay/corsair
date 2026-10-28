# PLAN-0129: Bounded producer skills and mechanical tools

Status: completed bounded implementation and measurement; native component qualified on the physical Mac, live-model reliability remains unpromoted. No publication performed.

## Authorization and ownership

User authorized implementing the skill/tool-first recommendation on the existing local `manus/just` tree. Preserve the uncommitted outcome/Node/Java evolution and PLAN-0128 work. No commit, push, model/provider substitution, oracle change, new recipe, target execution permission, or negative-policy relaxation is authorized here.

Parent owns role-local helper implementation/composition, metadata/identity, procedural guidance, consumer updates, private native replay/evaluations and public records. An independent test owner may create only `tests/unit/test_producer_helpers.py` and its private result note. No shared-file concurrent editing.

## Bounded component

- Add exactly `preview_invocation` and `relative_path` as ordinary episode-bound native ADK callables under `agents/producer/tools/`, exported/composed explicitly alongside unchanged source readers and native skill loaders. The auditor remains loader-only and outcome-blind.
- `create_preview_invocation(producer_input)` returns async `preview_invocation(payload, tool_context)`. It constructs the declared Python kwargs or Node/Java inserted positional args, checks JSON size/Java String constraints, preserves operator-fixed values and returns bounded mechanical-only data. It never calls/imports/compiles the target or evaluates control behavior.
- `create_relative_path(producer_input)` returns async `relative_path(base_root, target_path, tool_context)`. It computes POSIX lexical relative paths in memory only. Reject empty/nonabsolute paths, double-leading slash ambiguity, backslash/NUL and oversized inputs/output. Do not inspect the host filesystem, guess source semantics, claim reachability/bypass or mutate a submission.
- Keep one canonical ProducerDecision/Submission schema and native ADK execution/accounting. No custom loop, mandatory tool broker, string repair, registry, executor or scripted runtime skill. Optional helpers count against the existing tool/LLM limits.
- Improve the existing source-grounding procedure using general source/ABI and guard reasoning, helper guidance and call-budget awareness. Keep essential invocation data in the packet; do not depend on optional calls for evidence enforcement. Do not change operator ownership of controls or shrink the output contract in this iteration.
- Bind helper implementation/capability identity to packaged resources. Preserve auditor instruction/procedure/schema/tool surface. Update current docs describing the approved producer capabilities.

## Frozen measurements

1. Save hashes of the current public source, fixtures/datasets and baseline guidance/tool composition privately. The actual comparison retained a hash-verified pre-helper source-package snapshot rather than a baseline wheel extraction; final production wheel qualification remains separate.
2. Replay saved prior producer proposals through trusted hardened Docker only, with new operation identities. Retain all original 20 rows, provider errors, no-valid-output rows, exact-match classes and actual native control/adversarial validity. Do not reinterpret invalid/error attempts as held results or edit old immutable results.
3. Compare revised skill-only against skill-plus-tools on identical unchanged Node/Java producer fixtures and existing reviewed model/settings/budgets, five repeats each. The skill-only arm uses the real production ADK runner/factory assembled with the saved pre-helper capability composition; it is a deliberately separate private diagnostic arm, not a production toggle/back-end. No paid run is repeated automatically after lost/uncertain completion.
4. Retain original Python producer diagnostics and independent outcome-blind auditor safety checks. Track native tool uptake, mechanical validity, control/adversarial observations, exact-match diagnostics, token/call totals and role seconds. Cost stays unknown if unavailable.
5. After independent gates, run one distinctly identified bounded real composed Node/Java repeat; preserve failures and full finite protocol. Do not promote majority reliability or close ISSUE-0014 on one good run.

## Qualification

Run focused helper and consumer tests with genuine scripted ADK; test output/input bounds, pure no-I/O behavior, fixed-argument protection, canonical schema, source/auditor isolation, ordinary callback budgets, unsupported inputs and identity changes. Run `nix develop --no-update-lock-file --command just sync check`, reviewed real Docker/Temporal/CLI/replay/full native gates, final affected tests and frozen evaluations after cleanup, then wheel/sdist build and outside-checkout packaged-resource validation. Keep current-revision Linux/remote CI explicitly unrun unless actually executed. Generated/private state stays ignored and excluded from packages.

## Actual results

Implemented both role-local helpers, exact metadata/factory/toolset admission, packaged helper-byte provenance, concise general procedure and current capability documentation. Auditor, canonical contracts, Docker observer/verifier, workflows and finite-protocol policy are unchanged. Native ADK tests cover calls, schema-completion fallback, byte/type/path bounds, no-I/O behavior, fixed-value protection and budgets. No custom orchestration or production experiment toggle was added.

The [sanitized experiment](../../../../evals/experiments/2026-10-26-producer-skills-and-tools.md) records complete denominators and identities. Five-repeat revised skill-only diagnostics matched 4/20 exact payload pairs and produced 8/20 valid natively executed pairs; the helper-surface arm matched 12/20 and produced 16/20 valid pairs, with 17/20 healthy controls. Native replay of prior PLAN-0128 proposals found 8/20 valid pairs. Neither new live arm called a tool; causal helper benefit is unproved, and the helper-surface median role episode was slower (6.16s vs 4.69s). Cost remains unknown. java01 still had only 2/5 valid pairs.

The separate Python producer cohort matched 1/3 exactly, with 3/3 healthy controls and 2/3 valid native pairs; its remaining execution error prevents a non-regression claim. The unchanged outcome-blind auditor safety cohort remained 12/12, including false-claim rejection, at its identical prior resource digest.

One new full production live ADK/Docker/Temporal batch resolved 2/4 (java01 DEMONSTRATED; java02 NOT_DEMONSTRATED after both required held rounds). Node cases remained incomplete after abstention/native error or an unfinished protocol; no negative clearance was manufactured. The CLI exited 1, the harness retained all reports and successfully cleaned up. All committed results were independently reconciled and re-scored. ISSUE-0014 remains open; prior failed and successful batches are preserved, not rewritten.

Commands/results:

- `nix develop --no-update-lock-file --command just sync check`: passed after explicit required local daemon access. Later `just check` and `git diff --check` passed.
- `.venv/bin/pytest -q -W error` over `test_producer_helpers`, `test_agents`, `test_agents_runtime`, `test_model_settings`, `test_agent_skill_identity`, `test_agent_evaluator`, `test_auditor_guidance`: 70 passed, first final run 3.58s, post-record repeat 2.38s; no skips.
- Producer Node/Java arms: unchanged `node-java-producer.json`, five repeats each through the production evaluation module. Skill-only imported the hash-verified retained pre-helper package with identical revised instruction/procedure; helper arm used `nix develop ... just -- eval-agent producer ... --repeats 5` with current factory. Both diagnostic CLIs exited 1; completed files were recovered without resubmitting inference after terminal-session loss.
- Preserved Python producer: `just -- eval-agent producer evals/datasets/producer-expanded.json --repeats 1`, exit 1. Auditor safety: `just -- eval-agent auditor evals/datasets/auditor-expanded.json --repeats 3`, exit 0. All use the existing reviewed private settings/provider, with new report/artifact identities.
- Private native replay script: saved typed artifacts only, reviewed offline images, fresh immutable operation identities; all 20 rows per Node/Java cohort retained. Initial conservative stops were proven pre-execution Java payload-schema rejections with no intent, operation claim or container; only never-executed rows were continued under separate identities. No observed/uncertain operation was blindly repeated.
- First `nix develop ... just -- test-all -q -W error` with all explicit native gates/reviewed immutable images: 320 passed, 1 failed, zero skips in 360.58s. Sole failure was a stale producer capability-list assertion in `test_chain`; native execution/fix/evidence passed. That assertion was updated. The distinct final full retest passed **321 tests, zero skips, zero pytest warnings in 344.03s**, with XML/exit-code agreement. The original failed XML/log remains retained.
- Skill validator: passed using the absolute role-local directory; an initial relative argument failed because the utility prepended its default sandbox skill root. No validation success was claimed for that failed invocation.
- `just build`: wheel/sdist built and rebuilt after archiving. All 78 runtime source/resource bytes matched the wheel, private exclusions passed, helpers/resources/canonical schema loaded and worked outside the checkout. Existing cache/build-backend warnings remain explicit. The existing build backend does not include docs/evals records in these runtime distributions; public plan/experiment files are separately delivered and link-validated. Final `just check`, `git diff --check`, runtime-byte/privacy checks and deliverable-completeness checks passed without changing evaluated runtime bytes.

All 64 frozen public fixture/dataset hashes and auditor source bytes remained unchanged. Evaluated producer resource `51f416632051dc2f1645c668a1dd86b7fecc0956925870740a7e041b68f51a43`; unchanged auditor `da3221780152da734ebb983110871cd4968d42d52da7ccff0d61231096e348f1`; helper digest `011749b46bfb586162ea949a846c8fec955af09bb57b28967825858d10b07b25`. The task-owned SDK service/worker stopped, loopback listener closed, no task-labeled containers remained and SQLite backup integrity passed. Private state/claims/evidence remain retained and ignored; no unrelated cleanup occurred.

Local access denials and one permission-reviewer malfunction remain recorded. Current-tree Linux amd64 and remote CI are unrun. No commit/push, majority reliability, runtime speedup, general hostile-source observation integrity, exactly-once execution, full host-loss continuation, broad framework/patch verification or production readiness is claimed.
