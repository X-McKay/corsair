---
id: PLAN-0110
kind: plan
title: Native ADK Pydantic producer output
status: implemented
updated: 2026-10-25
related: [ISSUE-0009, HANDOFF-0142]
---

> Historical record. Commands, counts and status describe the recorded revision, not the current working tree. See [current work](../../README.md) for current guidance.

# Native ADK Pydantic producer output

User requests fixing failed validations using Pydantic and native Google ADK structured output. Preserve existing uncommitted physical-Mac test/docs changes and the prior named main stash. Work on current `manus/just` without publishing.

Use existing canonical `Submission` with nested `PlanRevision` as `LlmAgent.output_schema`. Keep two read-only source tools; remove custom submit validation/termination state instead of decoding string arguments or flattening the model. Enforce canonical Pydantic validation, dynamic round/parent checks, existing per-episode tools/model/time caps, external-oracle separation and unchanged Docker policy. Inspect actual SDK capability; configured native LiteLlm OpenAI-compatible Qwen route reports `output_schema_and_tools=True`. Models without that capability use ADK's own documented schema-tool handling, not application repair.

Baseline: frozen producer 0/3, nine model/nine tool calls, 11689 input/1713 output tokens; every final nested plan arrived as a string and was rejected. Frozen auditor 6/6. Frozen requests/oracles/budgets must not change.

Gates: native schema/factory/round/invalid-output/tool-budget and ADK fallback regressions; `just check`; unchanged producer/auditor frozen evaluations; then actual live producer/auditor/Docker/Temporal composition and external scoring; full native Mac suite, built wheel and exact owned cleanup. Preserve failed attempts and unknown accounting. Update issue, CURRENT and handoff with actual results.

Sources: https://adk.dev/agents/llm-agents/ documents native Pydantic output_schema and warns about model-dependent tools support. Installed ADK2.13.0 basic/schema processors and LiteLlm capability/response_format conversion inspected locally. No SDK fork/monkeypatch or new provider wrapper is needed.


## Completion and actual results

Implemented locally on manus/just. Native ADK output_schema/Pydantic replaced custom producer completion; the requested ports/adapters/contracts/evaluation organization is functional, not scaffolding. Strict Ruff/format/Just-format/ty pass. Complete physical-Mac suite with real Docker, Temporal and live auditor:134 passed in139.71s; final installed-wheel recheck1 passed in7.74s, sdist/wheel build succeeded. Frozen producer3/3; auditor6/6. Frozen request/oracle/source hashes, budgets and SDK/Nix locks unchanged. Full live model/worker/native batch2/3: original/fixed and conditional cases passed, safe follow-up probe retained ERROR/INCONCLUSIVE under ISSUE-0010. No hidden policy weakening or passing-live-accuracy claim. Linux current-local-revision CI remains unrun. See HANDOFF-0143 for commands, private evidence, exact cleanup and preserved local state. No commit/push/deployment performed.
