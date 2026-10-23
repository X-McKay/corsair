# Corsair

Corsair checks a reported security finding against an exact source revision and, when supplied, its fix. Its architecture is deliberately small: **one producer, a deterministic verdict kernel, and one outcome-blind auditor**. PydanticAI owns the agent loop; pytest owns the shared probe driver; existing language tools own native coverage; Docker owns execution isolation.

The producer submits a hypothesis, a replayable `build_script`, and one Python module declaring `CONTROL_PAYLOAD`, `EXPLOIT_PAYLOAD`, and `run_target(payload)`. The same function exercises the real target for either input. For Java, Node, Perl, Ruby, and C++, it invokes native subprocesses; target coverage never comes from the Python wrapper.

The kernel binds the reported file, checks probe structure, replays the build in a clean container, rejects changes to **any original source-tree entry**, and freezes the compiled source. Kernel support files are root-owned and read-only; source collisions at the reserved `.corsair` path are refused. Two fresh, unprivileged, **offline** containers then run control and exploit separately. The control must hold, the exploit must violate the probe's own security invariant, and **every claimed vulnerable-target line must execute in both**. Missing or ambiguous native evidence, an unrelated crash, and application assertions are not proof. Only then does the stateless auditor review the hypothesis and probe, without outcomes. Fixed-revision replay annotates the finding; it never changes the vulnerable-revision label.

## Quick start

Requirements: Linux, Docker, Python 3.12, and [uv](https://docs.astral.sh/uv/). Model credentials are not needed for kernel tests.

```bash
make sync             # pinned development environment
make check            # pinned lint and formatting checks
make test-offline     # contracts, parser regressions, scripted agents; no model or Docker required
make verify           # build Python image and verify the reviewed paired fixture
make images           # all six images; Node covers JavaScript and TypeScript
make test             # tests plus available real-runtime Docker checks
make benchmark        # all 385 generated twin cases through the real kernel; no model calls
```

For a smaller run, use `make benchmark LANGUAGE=java WORKERS=2`. `make benchmark-generate` only generates cases and explicitly reports that execution was not requested. Results are under `.runs/polyglot/`; `make cleanup` removes Corsair-labelled containers, and `uv run corsair cleanup --images` also removes cached sealed environments.

## Languages and build systems

| Target language | Native evidence | Included build/tool support |
| --- | --- | --- |
| Python | coverage.py | pip/setuptools; build recipes for uv, Poetry and pytest |
| Java | JaCoCo agent + CLI XML | JDK 21, Maven and Gradle; standard source/class layouts |
| JavaScript | V8 rendered to LCOV by c8 | Node 22, npm, ESM/CommonJS |
| TypeScript | c8 source-map remapping | TypeScript, tsx, npm and Vite |
| Perl | Devel::Cover database API | MakeMaker, Make, prove and cpanm |
| Ruby | SimpleCov resultset | Bundler and Rake |
| C++ | GCC gcov JSON | GCC, CMake, Make and Ninja; `--coverage -O0 -g` |

The operator-owned [runtime matrix](matrix.yaml) selects the image and native collector. Build-system commands belong in the submitted build script and [producer skills](src/corsair/agents/producer/skills), not framework-specific kernel branches. Target extensions disambiguate mixed-language trees. Unsupported toolchain versions or layouts fail honestly; the matrix is not a claim that every project or framework has been validated.

## Run the agents

Copy `config/providers.example.json` to your own ignored provider configuration, select explicit model profiles, and set the environment variable named by `api_key_env`. Never commit credentials or private endpoints.

```bash
make investigate CASE=cases/path-traversal-fixture PROVIDER=config/providers.local.json
make eval-dev PROVIDER=config/providers.local.json REPEATS=3
make eval-heldout PROVIDER=config/providers.local.json REPEATS=3
```

The producer has only `bash`, `read_skill`, and `submit`. Submission, shell, request, token, and timeout budgets are operator-owned. Runs retain progressive checkpoints, tool timings, bounded file-change metadata, instruction/skill/configuration hashes, gate results, full native reports and content-addressed logs. Oracles are evaluator-only and never enter agent context. Compare models only with frozen case sets, prompts, skills, budgets, and runtime images; tune on dev, not held-out.

`LIKELY_EXPLOITABLE` requires the vulnerable differential. `LIKELY_NOT_EXPLOITABLE` needs a configured number of **distinct clean negative submissions** (default two), not one unsuccessful attack. Otherwise the result is `INCONCLUSIVE`, `UNABLE_TO_RUN`, or `ERROR`. A model response is never itself a verdict.

## Optional proposal operations

```bash
uv run corsair seed --case CASE --target relative/source.py --vulnerability-class CWE-22 \
  --provider config/providers.local.json --output .runs/seed.json
uv run corsair optimize-skills --trace .runs/lite/RUN_ID/run.json \
  --provider config/providers.local.json --output .runs/skill-proposal.json
```

Both operations return schema-validated **review proposals**. They do not apply patches, mutate operator skills, install new policy, or claim that a proposed bug or rule is validated. Test and review proposals separately.

## Navigate the codebase

```text
src/corsair/
├── cli.py                         # Composition root: configure and connect adapters
├── agents/
│   ├── producer/
│   │   ├── agent.py               # PydanticAI factory and explicit capabilities
│   │   ├── agent.yaml             # Reviewable agent contract and allowlists
│   │   ├── dependencies.py        # Typed runtime context
│   │   ├── types.py               # Run output and bounded-stop types
│   │   ├── instructions/system.md
│   │   ├── tools/                # bash, read_skill, submit
│   │   └── skills/<name>/SKILL.md
│   ├── auditor/                  # Tool-free, outcome-blind agent
│   ├── bug_seeder/               # Tool-free bug proposal agent
│   ├── skill_crystallizer/       # Tool-free skill proposal agent
│   └── resources.py              # Shared spec/resource validation only
├── domain/                       # Immutable case, submission and evidence types
├── application/
│   ├── kernel.py                 # Deterministic verification gates
│   ├── investigation.py          # Bounded producer execution and stopping
│   ├── cases.py                  # Source requests; evaluator-only oracle loading
│   └── evaluation.py             # Frozen sets, scoring and metrics
├── ports/                        # Typed boundaries, no implementation selection
│   ├── sandbox.py
│   ├── inference.py              # Model assembly; SDK Model owns invocation
│   ├── scm.py
│   ├── artifacts.py
│   ├── framework.py
│   └── verification.py
├── adapters/
│   ├── sandbox/docker.py
│   ├── inference/openai.py       # Native SDK model/client lifecycle
│   ├── scm/git.py                # Pinned Git acquisition with hooks disabled
│   ├── artifacts/filesystem.py   # Content-addressed evidence and atomic JSON
│   └── frameworks/               # Native coverage SDKs and shared pytest driver
└── runtime/                      # Operator model settings and runtime matrix
```

Start with `cli.py` to see composition, then `application/kernel.py` for the verification path. Follow an agent's `agent.py` to its private tools, instructions and skills. To change Docker or Git behavior, go directly to the matching adapter rather than looking through agent code.

Dependencies point inward: concrete adapters implement ports; application services receive them explicitly; domain contracts know neither adapters nor agents. The kernel does not select Docker, a filesystem store or a coverage implementation. Agents use PydanticAI's existing `Model` interface, not another home-built model API. Architecture tests enforce these boundaries. Only genuinely shared resource validation is shared; the tool-free agents do not have empty `tools/` or `skills/` directories.

`images/` holds toolchains, `tests/` the regression suite, and `benchmarks/polyglot/` plus `tools/benchmark.py` the deterministic generator and runner. External leads remain separate in `benchmarks/catalog/` and `docs/benchmark-sources/`. Generated projects and private run evidence live under ignored `.runs/`, not in the source package.

## Evidence and limitations

The [polyglot benchmark guide](docs/polyglot-benchmarks.md) describes **55 twin cases per language**, 385 total, spanning 11 synthetic policy mechanisms and five payload variants. These are runtime/build/invariant regressions, **not 385 unique vulnerabilities or a measurement of model accuracy**. A separately sourced catalog contains 1,032 external candidates across the seven languages; those are leads, not executed Corsair cases. Real-framework evaluation requires authorized, reproducible imports with upstream versions, patches and license review.

Docker is the implemented execution backend, not a production OpenShell deployment. Hardened containers reduce risk but are not a guarantee against container escapes. Probe structure checks and a blind auditor are not an adversarial proof system: native reports are not cryptographic execution attestations, and model-authored builds and probes still require review. Original source entries must stay unchanged, so projects that deliberately rewrite tracked source during builds need an explicit policy decision rather than a silent exception. C++ fatal sanitizer aborts may lose coverage and remain inconclusive; Java nonstandard source layouts need explicit support. Build replay can access the network, while probes cannot. No tool bypasses an unavailable runtime, coverage failure, or provider refusal.

See the [architecture refactor](docs/architecture-refactor.md), [implementation contract](docs/spec-0090-implementation.md), [validation record](docs/validation.md), [original design](docs/design.md), and [earlier Python pilot](docs/pilot.md). This branch follows the agent-private layout and contract/evidence separation in `X-McKay/playbooks`; it is a review candidate, not a certification or merge approval.
