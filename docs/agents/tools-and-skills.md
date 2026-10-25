# Tools and runtime instructions

Agent capabilities are deliberately smaller than the surrounding runtime. The producer receives two episode-private native ADK source tools and both roles receive only private native procedural-guidance loaders. The auditor has no source, execution, network, or external tools. Factory metadata and construction reject a surface outside these approved capabilities.

| Role | Capability | Permitted operation | Boundary |
| --- | --- | --- | --- |
| Producer | `read_file(path)` | Read one bounded, normalized relative text file from the already admitted immutable source snapshot. | No arbitrary host path, write, execution, or new source admission. |
| Producer | `list_files()` | List bounded regular relative files in that same validated snapshot. | No archive mutation, shell, or target invocation. |
| Producer and auditor | `load_skill(name)` | Load an explicitly admitted role-local `SKILL.md` procedure from the installed package. | Role-filtered private catalog only; no dynamic directory, remote, or user-supplied skill loading. |
| Producer and auditor | `load_skill_resource(skill, resource)` | Load an explicitly admitted packaged resource for an admitted role-local procedure. | No scripts, code execution, asset execution, environment injection, or state transfer. |

The producer receives a read capability created for one `ProducerInput`; it cannot choose a host directory or obtain the broader source-admission capability. Tool output is bounded by the configured tool-output budget. Source content is untrusted data, so embedded instructions do not override the packaged role instruction. The auditor reads only its supplied packet and cannot obtain additional source context.

## Private procedural skill loading

Role-local `toolsets.py` composes the producer's static source readers, where applicable, with native Google ADK `SkillToolset`. The skill catalog is initialized in `EAGER` mode from an explicit allowlist of package resources. The producer can load only `source-grounding`; the auditor can load only `semantic-review`. A resource call is available only for an admitted resource of an admitted skill. The current procedures need no scripts, templates, or supplemental resources.

A skill loader is not a generic tool registry or execution environment. It makes Markdown guidance available to the current role context; it cannot call a source reader on the auditor's behalf, run code, create a target probe, alter fixed arguments, access an oracle, or persist state. Each successful loader call is counted against the existing or explicit finite ceilings and recorded only as bounded safe loader metadata. Skill content and admitted capability data contribute to configuration and immutable operation identity; unknown usage or cost remains unknown.

## Not agent tools

The following are trusted runtime or evaluation components, not capabilities an agent can call:

- **Source admission and snapshot storage:** operator-owned local source admission creates a hash-verified snapshot before the producer reads it. The current SCM boundary is local snapshots, not a remote forge client.
- **Sandbox execution:** the trusted verifier invokes the configured Docker SDK sandbox with the operator-owned recipe. The sandbox never appears as a producer or auditor tool.
- **Artifacts, evidence, and disposition:** immutable artifact storage, receipt verification, and policy decisions are outside both agent contexts.
- **Temporal coordination:** workflows own durable rounds, activity scheduling, cancellation, and recording. Agents run only within the normal bounded activities.
- **Oracles and scoring:** frozen labels and external scoring are evaluator inputs. They are never provided to the producer, auditor, tools, skills, or workflow packet.

There is no production MCP integration, remote forge connector, generic tool catalog, dynamically discovered skill directory, code executor, remote skill source, or agent-run environment. Adding a runtime procedure requires an implemented factory, allowlist, identity, accounting, validation, and packaged-resource change; a directory convention alone grants no capability.

## Runtime instructions versus procedural guidance

The model always receives the packaged system instruction associated with its role plus the bounded activity packet. The system instruction owns the role's always-on safety and output boundary. A procedural skill is optional, role-private guidance that the native loader places into the same episode context after an explicit tool call. Neither replaces the other, and loading guidance does not execute the guidance.

Corsair's `agent.json` is validated JSON role metadata. A skill's `SKILL.md` has YAML frontmatter (`name` and `description`) used by the native skill mechanism. These are not an ADK YAML Agent Config and do not create a Corsair DSL. The authoritative behavior remains the native Python factory, canonical Pydantic contract, and trusted runtime.

For the role architecture and structured-output rules, read [the overview](overview.md); for changes, read [development](development.md); and for frozen checks, read [evaluations](evaluations.md). Current plans are available through the [plans index](../plans/README.md).

## Developer skills are not runtime capabilities

The shared [coding-agent workflows](../development/coding-agent-workflows.md) use canonical development-only files under `.agents/skills`. Claude Code discovery aliases point to those files; Codex reads the canonical location. These skills help maintainers follow [extension qualification](../guides/extensions.md) and frozen evaluations. They are not installed in the Corsair wheel, loaded into producer/auditor prompts, exposed through `SkillToolset`, or granted execution/publication permissions.

## Core preload versus optional progressive loading

The required role procedure is parsed from its private packaged SKILL.md by native ADK during controlled factory assembly and its instruction body is present in LlmAgent.instruction before the first model request. This avoids relying on a structured-output model to choose a loading tool. Usage.skills_preloaded and agent.skill_preloaded describe actual preparation, not model compliance or tool execution. Optional native load_skill refreshes and load_skill_resource reference requests remain available within finite root/episode budgets; only successful model-requested loads populate Usage.skills_loaded, and their dispatches count as tool calls. The configured provider skipped optional loading in the earlier diagnostic stage; those reports remain retained rather than rewritten as successful tool use.
