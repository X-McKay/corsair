# Agent packages and ports/adapters

This refactor follows the agent-private layout in [Playbook chapter 2](https://github.com/X-McKay/playbooks/blob/main/agent-playbook/02-reference-architecture.md) and the [Python implementation profile](https://github.com/X-McKay/playbooks/blob/main/implementation-profiles/python/README.md). The complete annotated directory tree is in the [README](../README.md#navigate-the-codebase).

It continues `feature/differential-oracle-spec-0090` from `a1f44519d3650b768bec7351e8fa05c38b4aec2d`. It changes code ownership and composition, not native evidence requirements, verdict semantics, provider policy, budgets or container isolation. Portable resource metadata and explicit capability-drift validation are deliberate additions. Public CLI commands and proposal JSON shapes are preserved; old flat Python import paths are deliberately removed rather than retained as compatibility shims.

## Find a responsibility

| Responsibility | Owner |
| --- | --- |
| Assemble approved integrations and commands | `src/corsair/cli.py` |
| Build a producer/auditor/proposal SDK agent | `agents/<name>/agent.py` |
| Review an agent contract or its prompt | `agents/<name>/agent.yaml`, `instructions/system.md` |
| Change a producer-private capability | `agents/producer/tools/{bash,read_skill,submit}.py` |
| Change producer procedures | `agents/producer/skills/<name>/SKILL.md` |
| Define data contracts and pure verdict rules | `domain/{case,verification,artifacts,policy}.py` |
| Coordinate an investigation or native verification | `application/{investigation,kernel}.py` |
| Parse a case, freeze an oracle set or score results | `application/{cases,evaluation}.py` |
| Understand an integration's required operations | `ports/{sandbox,inference,scm,artifacts,framework,verification}.py` |
| Change Docker, Git or SDK client behavior | The matching `adapters/` package |
| Add/change native target coverage | `adapters/frameworks/` plus its `ports/framework.py` contract |
| Configure toolchain/model selection | `runtime/`; root `matrix.yaml` points to its one packaged owner |

The producer has an actual dependency context, output types, private tools and ten private skill packages. Auditor, bug seeder and skill crystallizer are tool-free, so they do not have empty tools/skills directories. Proposal agents do not acquire write authority. `.agents/skills/` is reserved for development-agent guidance; runtime procedures are not mixed into it.

## Dependencies and composition

`cli.py` selects actual adapters. Application services receive the sandbox, framework and artifact implementations explicitly. Git requests require an injected SCM; local source requests do not instantiate Git unnecessarily. Model/client assembly has an inference port, but model invocation uses PydanticAI's existing `Model` interface directly. No second model API is introduced.

Application orchestration can assemble agent factories. Agents and private tools depend on domain contracts and ports, not application orchestration or concrete adapters. Native adapters consume domain evidence types; the kernel does not import its own implementations lazily. Pure stopping rules live in `domain/policy.py`, so model tools can request verification without owning or selecting verdict infrastructure.

There is no DI container, workflow engine, generic repository base class, speculative backend catalog or fallback backend. Native SDKs, the Git CLI, standard filesystem primitives and existing PydanticAI capabilities remain the implementations. Shared agent code is limited to validated resource access; capabilities stay with their consuming agent.

## Agent resources

Factories lazily load packaged specs and instructions and reject tool/skill capability drift. Resource paths are installed-package-relative and reject traversal and physical symlinks. Skills follow `skills/<name>/SKILL.md` with `name`/`description` frontmatter. The model-visible `read_skill` result remains the original body, not extra YAML metadata. Producer/auditor instruction bytes and all ten original skill bodies are unchanged.

Specs, prompts and skills are included in both source distributions and wheels. An automated test extracts a built wheel outside the checkout, loads all four specs/prompts and ten skill packages, constructs SDK agents using `TestModel`, reads the runtime matrix and checks CLI help. Import/factory tests prohibit external subprocess/network effects and import-time instruction/skill reads. Investigation manifests now include agent-spec identities alongside effective instructions, skills, models, runtime and budgets.

## Developer loop

```bash
make sync
make check
make test-offline
make images
make test
make benchmark LANGUAGE=java WORKERS=2
```

For another execution backend, implement `ports/sandbox.py` and wire it at the composition root. For a new coverage collector, implement `ports/framework.py`, register it in the adapter registry and add a reviewed runtime row/image. Neither requires language-specific kernel branches or changes to agent tools. Add runtime capabilities only alongside a consuming agent and update its allowlist and regression tests.

## Validation

The first complete refactored end-to-end run passed 211 tests, including real Docker security and functional checks. The post-cleanup run passed 212 tests in 73.83 seconds. After the final pure-policy extraction and stricter dependency-boundary test, the full suite passed 213 tests. Independent static review found no architecture blockers and identified three optional cleanups; all were implemented: the unused SDK workspace surface was removed (208 lines from the Docker adapter), the private model builder now requires a managed client, and ownership tests validate metadata rather than pinning one owner. The final simplified code passed **213 tests in 73.22 seconds**. `make check`, the dependency-lock check, installed-wheel resource checks and passive-import/factory checks also passed. No runtime dependencies were added; the unused direct AnyIO declaration was removed while the SDK retains its own transitive dependency.

One production-kernel twin case passed locally in each of Python, Java, JavaScript, TypeScript, Perl, Ruby and C++. Every one of the 385 generated fixture submissions and both source-tree identities matches the retained pre-refactor benchmark record exactly. The complete seven-language CI benchmark will be rerun on the published implementation and recorded here after completion; retained original benchmark results are not relabelled as new execution evidence.

Live model accuracy remains unclaimed: the previously recorded provider refusal is not bypassed by this refactor, and scripted SDK tests or native fixture passes do not establish live-agent success. Historical implementation evidence remains in [validation.md](validation.md) and [benchmark-results.json](benchmark-results.json).
