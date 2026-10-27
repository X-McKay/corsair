# Tools and runtime instructions

Agent capabilities are deliberately smaller than the surrounding runtime. The producer receives exactly two episode-private native ADK source tools and no skill loader. The auditor has no tools at all: no source, execution, network, external or skill-loading tool. Each role's procedure is preloaded into its instruction. Factory metadata and construction reject a surface outside these approved capabilities.

| Role | Capability | Permitted operation | Boundary |
| --- | --- | --- | --- |
| Producer | `read_file(path)` | Read one bounded, normalized relative text file from the already admitted immutable source snapshot. | No arbitrary host path, write, execution, or new source admission. |
| Producer | `list_files()` | List bounded regular relative files in that same validated snapshot. | No archive mutation, shell, or target invocation. |

The producer receives a read capability created for one `ProducerInput`; it cannot choose a host directory or obtain the broader source-admission capability. Tool output is bounded by the configured tool-output budget. Source content is untrusted data, so embedded instructions do not override the packaged role instruction. The auditor reads only its supplied packet and cannot obtain additional source context.

## Private procedural skill loading

The producer's role-local `toolsets.py` returns only `read_file` and `list_files`. The auditor has no `toolsets.py`. Each factory parses its admitted procedure (`source-grounding` or `semantic-review`) through the admitted native loader path and preloads it into the instruction, and `AgentSpec` rejects any loader tool on either role. No `SkillToolset` is composed: for the producer it would only re-offer the same reference-free text and add ADK's generic "load the skill first" guidance and two loader declarations (about 3.3 KB) to every request; for the auditor, having no tools lets ADK send `AuditResult` as the response schema on every route, so a review is one JSON-mode request with no `set_model_response` round trip and none of the roughly 2.4 KB of generic skill-tool guidance. A model-invented loader call is a native unknown-tool error (producer, charged to the ordinary tool budget) or stopped by the zero tool budget (auditor). The current procedures need no scripts, templates, or supplemental resources.

A preloaded procedure is not a generic tool registry or execution environment. It is Markdown guidance in the role instruction; it cannot call a source reader, run code, create a target probe, alter fixed arguments, access an oracle, or persist state. Skill content and admitted capability data contribute to configuration and immutable operation identity; unknown usage or cost remains unknown.

## Per-class references

Each role's skill carries a small set of data-only `references/*.md` notes, one per vulnerability class (path confinement, command/argument injection, SSRF and host allowlists, deserialization and code injection, error/exception exposure, mass assignment). A note says what to read in the source and how to reason about the benign and adversarial value for the recipe's `payload_parameter` (producer), or what each rubric rule checks for that class (auditor). The notes are admitted through the same bounded resource path as `SKILL.md`: visible Markdown, no scripts, assets, or state injection, each within its byte ceiling, and every byte hashed into `runtime_skills_digest` so adding or editing a note changes the role's runtime identity. They are **not** preloaded into the role instruction, so the per-call system prompt is unchanged.

The same packaged notes reach a role two independent ways; an operator keeps whichever the deployment uses:

- **Trusted-code selection (primary).** `select_reference` in `agents/resources.py` is a pure function that reads only the finding's title and description and the recipe kind, scans a fixed, documented keyword table, and returns at most one note for the matched class (or nothing when the class is unclear or the recipe kind has no packaged notes). A recipe kind whose property is fixed by the recipe itself (`python.command_sentinel/1`) selects its own `command-sentinel.md` note before the class table is consulted. The selection tables are hashed into `runtime_skills_digest` with the note bytes, so changing which kinds or classes receive a note changes both roles' runtime identity. The producer and auditor packet builders append that one note, bounded, under a `## Class reference` heading marked as data. This path needs no loader tool, so it works where the `SkillToolset` is removed. It reads no oracle, outcome, or model output, so it is safe for the outcome-blind auditor.
- **On-demand loading (secondary).** Where the `SkillToolset` loaders are present, the model may call `load_skill_resource` for one admitted note when the class is clear; the call counts against the finite loader budget and returns the same packaged text. The preloaded `SKILL.md` tells the model the matching note may already be in the packet, so it does not spend a call re-fetching it.

## Not agent tools

The following are trusted runtime or evaluation components, not capabilities an agent can call:

- **Source admission and snapshot storage:** operator-owned local source admission creates a hash-verified snapshot before the producer reads it. The current SCM boundary is local snapshots, not a remote forge client.
- **Sandbox execution:** the trusted verifier invokes the configured Docker SDK sandbox with the operator-owned recipe. The sandbox never appears as a producer or auditor tool.
- **Artifacts, evidence, and disposition:** immutable artifact storage, receipt verification, and policy decisions are outside both agent contexts.
- **Temporal coordination:** workflows own durable rounds, activity scheduling, cancellation, and recording. Agents run only within the normal bounded activities.
- **Oracles and scoring:** frozen labels and external scoring are evaluator inputs. They are never provided to the producer, auditor, tools, skills, or workflow packet.

There is no production MCP integration, remote forge connector, generic tool catalog, dynamically discovered skill directory, code executor, remote skill source, or agent-run environment. Adding a runtime procedure requires an implemented factory, allowlist, identity, accounting, validation, and packaged-resource change; a directory convention alone grants no capability.

## Runtime instructions versus procedural guidance

The model always receives the packaged system instruction associated with its role plus the bounded activity packet. The system instruction owns the role's always-on safety and output boundary. A procedural skill is role-private guidance preloaded after the system instruction in the same role instruction. Neither replaces the other, and preloading guidance does not execute the guidance.

Corsair's `agent.json` is validated JSON role metadata. A skill's `SKILL.md` has YAML frontmatter (`name` and `description`) used by the native skill mechanism. These are not an ADK YAML Agent Config and do not create a Corsair DSL. The authoritative behavior remains the native Python factory, canonical Pydantic contract, and trusted runtime.

For the role architecture and structured-output rules, read [the overview](overview.md); for changes, read [development](development.md); and for frozen checks, read [evaluations](evaluations.md). Current plans are available through the [plans index](../plans/README.md).

## Developer skills are not runtime capabilities

The shared [coding-agent workflows](../development/coding-agent-workflows.md) use canonical development-only files under `.agents/skills`. Claude Code discovery aliases point to those files; Codex reads the canonical location. These skills help maintainers follow [extension qualification](../guides/extensions.md) and frozen evaluations. They are not installed in the Corsair wheel, loaded into producer/auditor prompts, exposed through `SkillToolset`, or granted execution/publication permissions.

## Core preload versus optional progressive loading

The required role procedure is parsed from its private packaged SKILL.md by native ADK during controlled factory assembly and its instruction body is present in LlmAgent.instruction before the first model request. This avoids relying on a structured-output model to choose a loading tool. Usage.skills_preloaded and agent.skill_preloaded describe actual preparation, not model compliance or tool execution. Neither role offers optional progressive loading any more, so Usage.skills_loaded is always empty; it is not rewritten as successful tool use.
