# HANDOFF-0149: consolidated role-local agents and native runtime procedures

## Implemented scope

`manus/just` includes every latest recommendation head, the pending extension/developer-skill guidance and the role-local agent refactor. Private factories, agent.json metadata, canonical contracts.py identity views, toolsets.py, instructions/ and procedural skills/ belong to each role; producer read_file and list_files live in separate tools/ modules. No empty auditor source-tool package, duplicate wire model, dynamic capability registry, replacement agent loop, executable runtime skill, host target execution or new permission was added.

Core procedure bodies are loaded through native ADK from reviewed built-package resources and included in LlmAgent.instruction before generation. The model may optionally use role-filtered native load_skill/load_skill_resource; no scripts/assets/executor is admitted. Bounded Usage.skills_preloaded and agent.skill_preloaded record preparation independently of successful agent-requested Usage.skills_loaded and charged tool calls. A model not requesting a tool does not become fake tool usage, and preparation is not proof the model complied.

The old one-call/tool-free audit ceiling changes explicitly to at most two LLM requests and four guidance-tool calls, always capped by actual remaining root budgets. The auditor-runtime-budget-v1 Temporal patch preserves the original five-key activity payload and legacy guard for older replay histories. Native replay coverage is not a claim of complete old in-flight or host-loss continuation. Changed skill/resource/risk bytes participate in the existing capability/intent/evaluation identity.

## Final verified gates

- `nix develop --no-update-lock-file --command just check`: pinned Ruff lint/format, Just format, pinned ty with warnings failing and maintained documentation checks passed.
- Full `just -- test-all -q -W error` with real Docker, native SDK-owned Temporal servers, configured live auditor, VM-shared TMPDIR, CORSAIR_TEST_IMAGE selecting the current consolidated review image and CORSAIR_TEST_LONG_PROBE=1: **209 passed,0 failed,0 skipped** before and after final cleanup. Includes native producer/auditor, workflow/replay, actual CLI processes,121-second probe and fresh installed-wheel consumers.
- Fresh `just build` wheel/sdist excluded private/generated roots. The wheel's role-private skills and canonical identity views loaded from an actual directory outside the checkout using the root interpreter; no second persistent environment was created.
- All original/expanded frozen datasets/fixtures and uv/flake pins plus trusted native driver remain unchanged. Only public roots were staged; state, raw evidence/reasoning, model configuration, caches and delivery archives are ignored and excluded.

## Preserved failures and live qualification

The first full native stage was205 passes/3 failures: two nested AgentSpec provenance JSON serialization errors and a long-probe test selecting the older image. These were fixed via Pydantic model_dump and explicit current image selection without changing the scorer, fixtures or user tags. The corrected optional-loader stage passed208 native tests but recorded no optional load in30 isolated model attempts; those are retained, not counted as used skills. This prompted mandatory native procedure preload.

The final original producer scored2/3, original auditor2/6, expanded producer3/9 and expanded auditor6/12; all30 attempts recorded genuine procedure preload, no successful model-requested load and no operational failure. The once-submitted full live batch scored2/3: vulnerable case01 abstained and missed; safe case02 correctly stayed INCONCLUSIVE; case03 retained native component evidence and CONDITIONAL resolution. No workflow was resubmitted after terminal-handle loss. Cost remains unknown. No live-model baseline is promoted; [ISSUE-0013](../../active/ISSUE-0013-runtime-procedure-live-quality.md) and [ISSUE-0012](../../active/ISSUE-0012-producer-decision-live-quality.md) remain open.

## State and publication boundaries

One canonical root .venv was retained. Only task-owned worker/Temporal services were stopped after completed work; source/evidence/old claims were not pruned. The stopped task SQLite database receives a verified backup under ignored .state; forced service-stop status is not host-loss qualification. The original user Docker baseline tag is unchanged and unrelated services/workloads are untouched. Historical main work and its saved stash remain preserved.

The user authorized one normal manus/just commit/push, including the consolidated history. Main is not merged or modified. Exact commit, remote CI and final source/wheel bundle are separate delivery receipts; do not infer current-tip CI from earlier heads. [Native/evaluation receipt](../../../../evals/baselines/qualifications/qualification-agent-runtime-layout-2026-10-25.json) records exact source/resource identity and failed gates without private provider data.
