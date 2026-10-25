# Coding-agent workflows

Corsair keeps development-only instructions in the repository so coding agents can follow the same bounded implementation and evaluation discipline as maintainers. These guides are not runtime resources: adding or invoking one does not install a model skill, MCP server, provider, tool, plugin, or permission in Corsair. The runtime boundary remains documented in [tools and runtime instructions](../agents/tools-and-skills.md).

## Native skill discovery

The canonical public skill folders live in [`.agents/skills/`](../../.agents/skills/). They are intentionally small, link to authoritative repository guidance, and contain no copied runtime prompts, private settings, credentials, automation hooks, or model-running scripts.

| Coding agent | Native repository discovery | Explicit invocation example |
| --- | --- | --- |
| Codex | Read `.agents/skills/` | In a Codex prompt, use `$corsair-development` for a bounded code change or `$corsair-evaluations` for a frozen evaluation task. |
| Claude Code | Read `.claude/skills/`, whose two directory links point relatively to the canonical `.agents/skills/` folders | In Claude Code, use `/corsair-development` or `/corsair-evaluations`. |

The Claude folders are relative directory symlinks, not duplicate instructions or user-global installs. This documents repository layout and supported native discovery only; it is not an interactive Claude/Codex benchmark.

## Choose the workflow

Use [`corsair-development`](../../.agents/skills/corsair-development/SKILL.md) to plan, implement, review, or package one bounded repository change. Start with [AGENTS.md](../../AGENTS.md), [development conventions](conventions.md), [development testing](testing.md), and [extension qualification](../guides/extensions.md). Keep canonical schemas in one place, use installed SDKs rather than replacement frameworks, preserve private state and other contributors' work, and test before cleanup and again after cleanup.

Use [`corsair-evaluations`](../../.agents/skills/corsair-evaluations/SKILL.md) to run or revise a frozen producer, auditor, or composed evaluation. Start with [agent evaluations](../agents/evaluations.md) and the [baseline policy](../../evals/baselines/README.md). State one hypothesis, preserve inputs, hashes, labels, cohort membership, denominators, abstentions, and failures, and keep original, expanded candidate, and safety/composed cohorts distinct. An agent cannot promote a baseline, loosen a policy, or publish a result.

## Use maintained commands

Run commands from the repository root after following [development setup](setup.md). Use only the command that matches the boundary actually exercised:

```bash
just check
just -- test -q -W error
just build
```

For an intentionally configured isolated live-model diagnostic, use the installed evaluator with an explicit settings path and repeat count:

```bash
just -- eval-agent producer evals/datasets/producer-dev.json \
  --settings /operator/settings.json --repeats 3
just -- eval-agent auditor evals/datasets/auditor-dev.json \
  --settings /operator/settings.json --repeats 3
```

Do not run a model merely because a skill exists. Docker, Temporal, and live-provider checks each require their own explicit prerequisites; the exact commands and qualification limits are in [development testing](testing.md) and [agent evaluations](../agents/evaluations.md). Record provider/configuration identity and unknown cost rather than inventing a fallback or treating missing telemetry as zero.

## Deliver a bounded result

Keep the current plan and evidence limits visible through the [plans index](../plans/README.md). Report exact commands, results, skips, failures, unrun prerequisites, configuration identity, and remaining risk. Never commit `.state/`, `.runs/`, credentials, raw model reasoning, private diagnostics, caches, or scratch material. Build and inspect the exact authorized public package only after the final affected tests pass; do not grant publication or deletion authority to an agent.
