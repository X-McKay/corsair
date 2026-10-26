# Agent packages and runtime resources

Corsair packages two concrete ADK roles. This guide describes the implemented target layout for private role resources; it does not define a generic agent-package format, a plugin system, or an additional configuration language. Start with [agent development](../agents/development.md), [tools and runtime instructions](../agents/tools-and-skills.md), and the [components map](../architecture/components.md).

## Target layout

```text
src/corsair/agents/
  __init__.py
  resources.py                         # shared validated package-resource helpers
  producer/
    __init__.py
    agent.json                         # validated Corsair role metadata
    contracts.py                       # object-identity re-exports from corsair.contracts
    factory.py                          # native LlmAgent construction
    toolsets.py                         # the two source tools (procedure is preloaded)
    instructions/
      __init__.py
      system.md                         # always-on producer instruction
    tools/
      __init__.py
      read_file.py                      # bounded admitted-snapshot reader
      list_files.py                     # bounded admitted-snapshot lister
    skills/
      source-grounding/
        SKILL.md                        # private procedural guidance
  auditor/
    __init__.py
    agent.json                         # validated Corsair role metadata
    contracts.py                       # object-identity re-exports from corsair.contracts
    factory.py                          # tool-free native LlmAgent construction
    instructions/
      __init__.py
      system.md                         # always-on auditor instruction
    skills/
      semantic-review/
        SKILL.md                        # private procedural guidance
```

The auditor intentionally has no `tools/` directory and no `toolsets.py`. It receives no source reader, target executor, network client, external provider, or hidden tool through its packaged skill. There are no empty policy modules, runtime registries, code-execution packages, script resources, template resources, or placeholder backends in this layout.

## Metadata, contracts, and instructions

`agent.json` is Corsair JSON metadata. It identifies the role, approved capability names, system-instruction resource, schema reference, and existing governance metadata that the native factory validates. It is not an ADK YAML Agent Config.

Each `SKILL.md` begins with YAML frontmatter containing its `name` and `description`. That frontmatter identifies a private procedural resource to the native ADK skill mechanism. It is not a second agent definition, a YAML Agent Config, or a Corsair DSL. The factory remains ordinary native Python that constructs an `LlmAgent` with the installed ADK APIs.

Canonical Pydantic contracts live once in `corsair.contracts`. The two role-local `contracts.py` files expose the same objects for role-local imports; identity must be preserved. Do not copy a Pydantic model, derive an alternative wire schema, or add a compatibility decoder.

The system instruction and a procedure skill have different jobs. `instructions/system.md` is always loaded and retains the role's safety, output, and evidence boundary. `skills/*/SKILL.md` supplies the task procedure, preloaded after the system instruction. Guidance cannot change the always-on instruction, extend a packet, or execute itself.

## Native skill loading boundary

The producer's `toolsets.py` returns only the static, episode-private `read_file` and `list_files` functions. The auditor exposes no tool of any kind. Neither role composes a native ADK `SkillToolset` or exposes `load_skill` or `load_skill_resource`; each factory preloads its admitted procedure into the instruction.

A preloaded procedure becomes context for that single native episode. It is not a script runner, a code executor, a state-injection mechanism, a filesystem browser, an environment loader, a remote catalog, or an alternate agent loop. The current skills contain only `SKILL.md`; do not create a resource directory until a specific admitted, useful resource requires one.

Load only files that ship in the installed wheel. Do not read the checkout, a dynamic directory, a remote repository, or a user path at runtime. New or changed skill bytes, admitted resource digests, and capability data require qualification and must feed the existing configuration and immutable operation identities. Preloaded procedure names may enter bounded sanitized accounting; raw guidance, source, payload, model reasoning, usage, and unknown cost do not become evidence. Missing usage or cost remains unknown.

## Change and validation checklist

1. Keep a change within one role and use the existing native ADK factory and skill parser; do not invent a loader, scheduler, registry, or DSL.
2. Keep procedural guidance concise and imperative. Include frontmatter with only `name` and `description`; do not duplicate the role's system safety instruction or encode test fixtures, expected candidates, or evaluation oracles.
3. Add no scripts, executable assets, code tools, mutable state, or external access through a skill. Give the auditor no source capability.
4. Validate exact role allowlists, denied paths/resources, fresh-episode isolation, capability/resource bounds, preload accounting, canonical-contract object identity, and wheel resource loading outside the checkout.
5. Run `just check`, affected offline tests, and the required package/resource gate. Keep frozen fixture bytes, SDK/tool pins, recipe, evidence policy, and trusted Docker driver unchanged unless separately authorized and qualified.

Procedural skills do not prove model quality, target execution, evidence validity, or a negative security result. Use the [evaluation guidance](../agents/evaluations.md) for frozen role checks and the [current plans](../plans/README.md) for recorded qualification.

## Core preload versus optional progressive loading

The required role procedure is parsed from its private packaged SKILL.md by native ADK during controlled factory assembly and its instruction body is present in LlmAgent.instruction before the first model request. This avoids relying on a structured-output model to choose a loading tool. Usage.skills_preloaded and agent.skill_preloaded describe actual preparation, not model compliance or tool execution. Neither role offers optional progressive loading any more (no `load_skill` or `load_skill_resource`), so Usage.skills_loaded is always empty; it is not rewritten as successful tool use.
