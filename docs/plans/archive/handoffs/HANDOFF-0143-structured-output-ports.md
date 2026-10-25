---
id: HANDOFF-0143
kind: handoff
title: Native Pydantic producer output and ports/adapters organization
status: implemented
updated: 2026-10-25
related: [PLAN-0110, PLAN-0111, ISSUE-0009, ISSUE-0010, HANDOFF-0142]
---

> Historical record. Commands, counts and status describe the recorded revision, not the current working tree. See [current work](../../README.md) for current guidance.

# Native structured output and navigable package boundaries

## Local state and authorization

Work is in `/Users/al/git/corsair` on the existing `manus/just` branch, based on the pulled `80e2ff56` revision. This turn fixes the observed producer validation failure and implements the user's requested ports/adapters reorganization. Earlier physical-Mac docs/test changes remain preserved alongside these changes. Nothing was committed, pushed, merged or deployed during this local follow-up. The named original-main stash `0ce65a61` remains untouched; do not apply it over the redesign branch.

Read [architecture](../../../architecture/overview.md), [CURRENT](../CURRENT-before-doc-reorganization.md), [PLAN-0110](../plans/PLAN-0110-native-structured-output.md) and [PLAN-0111](../plans/PLAN-0111-ports-adapters-layout.md). Historical records retain their earlier code paths and are not current command instructions.

## Implemented

The producer declares the existing canonical Pydantic `Submission` and nested `PlanRevision` through native ADK `output_schema`. The custom submit tool, terminal flags, submission lock/state and provisional sandbox observations are removed. Its only executable capabilities are two immutable-source read tools. Native callbacks enforce and account for both ordinary tool calls and ADK's own schema-completion fallback. Canonical validation and dynamic round/parent checks remain; no string decoder, schema repair layer, contract relaxation or provider fallback was added.

An explicit Pydantic JSON union retains every supported JSON payload value type while giving native generation a meaningful top-level schema. Hypothesis/plan precede payload choices, with generic source-grounded argument-value/path guidance. A valid object is still not proof of semantic correctness. Frozen oracle labels, dataset/source digests, model budgets, exception policies and SDK/Nix pins were not changed to obtain passes.

The package now has `agents/`, `contracts/`, `ports/`, `adapters/`, `entrypoints/`, `policies/`, `workflows/`, `observability/`, `steps/` and `evaluation/`. Former `runtime/`, `tools/`, `policy/`, `contracts.py` and top-level `cli.py` are removed rather than retained as shims. All current imports, console entrypoint, packaged risk/driver resources, Docker build path and tests moved with their implementations. The standalone eval script became the installed `corsair.evaluation.agents` module, invoked by the same `just eval-agent` recipe.

The three SDK-free ports have actual consumers: inference in activities, source-reader/admission in producer tools/preparation, and sandbox execution in trusted verification. Concrete integrations are native ADK/Gemini/LiteLlm, local admitted snapshots and Docker. No fake GitHub, Azure DevOps, OpenAI or Bedrock module was added. The current SCM port means source snapshot capability, not implemented remote checkout. A small typed **Python** API (`entrypoints/api.py`) shares native Temporal workflow launch functions with the CLI; no HTTP service is implied.

## Actual validation

| Gate | Result |
| --- | --- |
| Locked Nix `just check` | Ruff lint/format, Just format and ty pass; warnings fail typing |
| Full physical Mac/Colima suite, real Docker/Temporal and live auditor enabled | **134 passed in139.71s**, no skips, warnings as errors |
| Final wheel/resource test after retired namespaces were removed | **1 passed in7.74s**, installed outside checkout |
| Fresh sdist/wheel | Built successfully |
| Unchanged isolated producer freeze | **3/3**, three repeats of one diagnostic case |
| Unchanged isolated auditor freeze | **6/6**, two cases repeated three times |
| Actual model/production-worker/Docker/Temporal batch, external native scorer | **2/3**, one retained safe-case execution error |
| Linux amd64 for these local changes | **Unrun**; prior CI success belongs to the earlier revision |
| Frozen inputs/SDK/Nix pins | No diff |

Reproduce the quality and suite gates inside `nix develop`, with the operator's existing Docker socket and a shared Mac `TMPDIR`:

```bash
just check
# Requires real Docker, the reviewed image, Temporal and an explicitly selected live settings file.
CORSAIR_LIVE_CONFIG=/path/to/settings.json just -- test-all -q -W error
just -- eval-agent producer evals/datasets/producer-dev.json --settings /path/to/settings.json --repeats 3
just -- eval-agent auditor evals/datasets/auditor-dev.json --settings /path/to/settings.json --repeats 3
just build
```

The local run used task-local uv environment/cache, the existing Colima socket, `TMPDIR` inside the shared repository, and a dedicated Temporal server at loopback17374 with queue `corsair-structured-20261025`. The production worker used the user-selected endpoint and explicit native non-thinking configuration, not a scripted model override.

Producer baseline: 0/3, 9 LLM/9 tool calls, 11689 input/1713 output tokens. Final: 3/3, 3 LLM/0 tool calls, 2910 input/845 output tokens. This narrow diagnostic is exact canonical payload matching, not population accuracy or general end-to-end speedup. Cost is unknown. The intermediate native-schema runs that validated objects but selected wrong payloads are retained, not erased or averaged out.

The first post-move offline/native attempts exposed stale tests expecting custom submit metadata and the old eval script/resource names; those expectations were updated alongside the moved implementations, and all final checks pass. A preflight command used an unsupported `--require-worker` flag and failed before workflow submission; the supported doctor command then passed. These attempts remain in private logs.

## Remaining live boundary

[ISSUE-0009](../issues/ISSUE-0009-qwen-nested-tool-plan.md) is resolved at the structured-object validation boundary. [ISSUE-0010](../../active/ISSUE-0010-live-safe-case-probe.md) is a distinct semantic limitation: in the actual three-case live batch, case01 completed `SUPPORTED` and its fixed demonstration was blocked, case03 completed `CONDITIONAL`, but case02 chose an invalid second-round adversarial probe after an initial held/held observation. It ended `ERROR` / `INCONCLUSIVE`; the scorer correctly retained one operational failure, with zero invalid positive evidence and zero forbidden labels. Do not turn that into a green negative-clearance claim.

A follow-up could evaluate a typed no-grounded-candidate outcome or better retry candidate selection in isolation. Do not loosen exception policy, change labels, inject reference payloads, hide errors or remove all iterative rounds to force a pass. Production hostile-target integrity, new languages/providers/remote SCM and host-loss recovery remain outside this pilot's qualification.

## Evidence and cleanup

Sanitized current receipt is `evals/baselines/qualification-structured-ports-2026-10-25.json`. Private commands, raw receipts and earlier failures remain in `.work/structured-output-20261025/` and `.runs/structured-output-20261025/`; these are not commit or publication material. The user-facing report is `outputs/structured-ports-20261025/REPORT.md`.

Every completed native observation confirmed cleanup. An actual Docker query showed no remaining `corsair.security=true` containers. The two exact task-owned worker/Temporal services were stopped after the completed workflows; service termination receipts and the absent loopback17374 listener confirm shutdown. Existing Colima and prior user services were not shut down. No workload credentials, Docker socket, network access, TLS bypass or weakened policy was added to target containers.
