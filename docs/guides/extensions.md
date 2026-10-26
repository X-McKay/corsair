# Extending Corsair safely

Corsair is a personal-use pilot whose running runtimes are **Python** and, on Linux amd64, a first **JavaScript** recipe, a **Ruby** secret-disclosure recipe and a **Perl** html-injection recipe, with operator-owned recipes and data-only JSON payload-pair proposals; the kernel materializes each recipe and runs the differential pair in an offline Docker container. The Perl recipe (`perl.html_injection/1`) is qualified on one frozen corpus row via a concrete `PerlRecipe` contract, a trusted `driver.pl` observer with a core-only line tracer, and the `deploy/perl/Dockerfile` image (see [the Perl corpus survey](../reference/corpus-perl.md)). Java rows, and the remaining Ruby and Perl rows, exist in the evaluation corpus but are not qualified runtimes. It is not a language-neutral scanner, generic framework harness, or autonomous repair system. Start from the [risk assessment](../../src/corsair/policies/risk.md), [security architecture](../architecture/security.md), and [testing guide](../development/testing.md) before proposing an extension.

An extension is qualified only for the exact source, recipe, runtime image, configuration, model, and host boundary that its evidence identifies. A healthy control or a non-disclosing adversarial observation is not a negative security clearance; failed, unavailable, invalid, or uncertain work remains explicit and inconclusive.

## Current support and the four separate concerns

The first implemented contract is [`PythonRecipe`](../../src/corsair/contracts/sources.py): a public function in a `.py` file, one model-controlled JSON payload parameter, operator-fixed keyword arguments, public fixtures, an expected control value, and allowed adversarial exceptions. [`Case`](../../src/corsair/contracts/sources.py) binds that recipe to the finding's file. The driver imports the pinned source module directly and invokes that callable; it does not install or resolve target dependencies. Python support therefore means **standard-library Python callables only**.

A second recipe is now qualified on Linux amd64: [`JavaScriptRecipe`](../../src/corsair/contracts/recipes_javascript.py) (`kind: "javascript.prototype_pollution/1"`), a prototype-pollution check at one exported dependency-free CommonJS callable. `Case.recipe` is a discriminated union on `kind`, with a missing tag resolving to the Python recipe for pre-union requests. The JavaScript observer `drivers/javascript/driver.mjs` runs `node --test` with the JUnit reporter and `NODE_V8_COVERAGE` line coverage inside `corsair-javascript:0.1` (`deploy/javascript/Dockerfile`, pinned `node:22.23.3-bookworm-slim` by digest); it installs nothing and uses no network at run time. The qualification is one real corpus row (`prototypepollution-a`) with real Docker evidence; macOS arm64 and the live chain are unrun. See the [JavaScript corpus survey](../reference/corpus-javascript.md) and [platforms](../reference/platforms.md#javascript-prototype-pollution-linux-amd64). JavaScript support therefore means **dependency-free CommonJS callables observed for prototype pollution only**.

A third recipe is qualified on Linux amd64: [`RubyRecipe`](../../src/corsair/contracts/recipes_ruby.py) (`kind: "ruby.secret_disclosure/1"`), the Python secret-disclosure check at one public Ruby module/class method (`receiver`, `function`) with the payload bound to one keyword argument. The observer [`drivers/ruby/driver.rb`](../../src/corsair/adapters/sandboxing/drivers/ruby/driver.rb) runs one fixed check under Ruby's built-in `Coverage` module and writes a one-case JUnit summary from a small fixed reporter inside `corsair-ruby:0.1` (`deploy/ruby/Dockerfile`, pinned `ruby:3.1-slim-bookworm` by digest); it installs nothing and uses no network at run time. The qualification is one real corpus row (`pathtraversal-b`) with real Docker evidence; macOS arm64 and the live chain are unrun. See the [Ruby corpus survey](../reference/corpus-ruby.md). Ruby support therefore means **standard-library Ruby methods observed for secret disclosure only**; Java and Perl rows remain corpus-only. Image selection per recipe kind is one `Settings.images` entry, not a new code path.
A second Python recipe, [`PythonCommandSentinel`](../../src/corsair/contracts/recipes_python.py) (`kind: "python.command_sentinel/1"`), asserts that the benign input does not create an operator-chosen private sentinel file under `/work` while an input that reaches command or code execution does; it shares the Python image and the one trusted [`driver.py`](../../src/corsair/adapters/sandboxing/driver.py), which selects a fixed per-kind test template, and both Python recipes share the Python-AST pre-model gates (`PYTHON_CALLABLE_RECIPES`). It runs the command-injection and code-injection corpus rows; the [Python corpus map](../reference/corpus-python.md) records which recipe each Python corpus row's property needs.

A second recipe is now qualified on Linux amd64: [`JavaScriptRecipe`](../../src/corsair/contracts/recipes_javascript.py) (`kind: "javascript.prototype_pollution/1"`), a prototype-pollution check at one exported dependency-free CommonJS callable. `Case.recipe` is a discriminated union on `kind`, with a missing tag resolving to the Python recipe for pre-union requests. The JavaScript observer `drivers/javascript/driver.mjs` runs `node --test` with the JUnit reporter and `NODE_V8_COVERAGE` line coverage inside `corsair-javascript:0.1` (`deploy/javascript/Dockerfile`, pinned `node:22.23.3-bookworm-slim` by digest); it installs nothing and uses no network at run time. The qualification is one real corpus row (`prototypepollution-a`) with real Docker evidence; macOS arm64 and the live chain are unrun. See the [JavaScript corpus survey](../reference/corpus-javascript.md) and [platforms](../reference/platforms.md#javascript-prototype-pollution-linux-amd64). JavaScript support therefore means **dependency-free CommonJS callables observed for prototype pollution only**; Java, Ruby and Perl rows remain corpus-only. Image selection per recipe kind is one `Settings.images` entry, not a new code path.

Do not describe the following as interchangeable. A change may need one, several, or all of them.

| Concern | It owns | It does not automatically supply |
| --- | --- | --- |
| **Language** | Source-file and callable/module semantics, recipe input constraints, and a trusted way to load and observe that language. | A framework's dependency graph, a runtime image, or a new evidence assertion. |
| **Framework** | The concrete application/runtime dependencies and deterministic operator-owned setup needed to reach a real API. | Permission to import targets on the host, a new language contract, or an expanded finding scope. |
| **Recipe** | One narrow operator-owned security property, fixed inputs, permitted model payload field, control expectation, and trusted assertions. | A generic test runner, arbitrary model-written code, or a generic language capability. |
| **Runtime image** | The reviewed interpreter, observer dependencies, immutable driver resource, and Docker execution environment used for a recipe. | A source-model contract, framework setup definition, or host/platform qualification. |

For example, a second Python callable recipe could be a recipe extension without adding a language. Supporting a web framework could require framework setup and an image update while remaining Python. Supporting a non-Python language requires a concrete recipe and trusted observer in addition to language and image work. Do not add an empty provider module, `LanguageRegistry`, generic backend, or speculative adapter merely to name future possibilities.

## Smallest incremental implementation map

Start with one bounded, observable property, not a broad claim such as "support framework X". A minimal conceptual example is a **second Python recipe** that invokes one fixed public callable with an operator-owned control path and one model-controlled scalar path; it is not an implemented JavaScript adapter or a promise of cross-language support.

1. **State the proposal precisely.** Document the language, framework (if any), callable/entry point, source files, one property, control case, adversarial case, permitted exceptions, required image, runtime, source limits, permissions, and component/application scope. Identify the target platform(s) individually: Linux amd64 and macOS arm64 are separate qualifications, not substitutes for one another.
2. **Add one canonical contract only when it represents real behavior.** Contracts belong in [`src/corsair/contracts/`](../../src/corsair/contracts/), are publicly re-exported by [`contracts/__init__.py`](../../src/corsair/contracts/__init__.py), and use the existing frozen, extra-forbidden `Contract` base. Preserve normalized relative paths, bounded data, JSON-only model payloads, and the rule that a payload may not override fixed operator arguments. `Case.recipe` is a discriminated [`Recipe`](../../src/corsair/contracts/sources.py) union on a stable `kind` tag (`PythonRecipe` plus `PythonCommandSentinel`, the latter in its own [`recipes_python.py`](../../src/corsair/contracts/recipes_python.py) module). Add a concrete, tested recipe as one more union member with its own `kind`; keep a pre-union, tag-less request valid by defaulting its discriminator to `python.secret_disclosure/1`. (A model *output* schema is different: [`ProducerDecision`](../../src/corsair/contracts/agents.py) is one flat object with a `kind` field because ADK's `set_model_response` tool turns the schema's top-level fields into typed tool parameters.) Do not create an empty union or duplicate a schema in an agent, driver, evaluator, or CLI.
3. **Preserve source admission.** Extend [`LocalSourceSnapshots`](../../src/corsair/adapters/scm/local.py) only if the new recipe needs an admitted artifact property not already present. Agent and sandbox reads must continue to use the immutable, digest-checked tar snapshot, never the source checkout path. Admission rejects symlinks, special files, unsafe paths, sensitive/oracle files, races, and excess files/bytes. A new source format does not relax these checks.
4. **Implement a recipe-specific trusted observer.** The observer receives an operator-created JSON job and data payload, writes or runs only its fixed test logic, and emits one strict JSON record. Its validated native report is the sole basis for verifier-owned `RoleObservation` facts. Prefer the language’s existing test/coverage SDKs and stable machine-readable reports; add only the small strict receipt projection required by this boundary, not a second test or tracing engine. The initial pattern is in [`driver.py`](../../src/corsair/adapters/sandboxing/driver.py): the control confirms public behavior and no private disclosure; the adversarial role checks the actual private value, captures native JUnit/exit status, and reports coverage. Model output must never become executable test/assertion code, expected secret material, a verdict, or a direct claim of evidence.
5. **Change the trusted image only for actual runtime requirements.** Put a framework runtime, package manager, pinned dependencies, and fixed observer prerequisites in the reviewed recipe image, not the host project environment. Target code is not imported, dependency-installed, or setup on the host. The current [`Dockerfile`](../../deploy/python/Dockerfile) contains only Python, pinned `pytest`/`coverage`, and the copied trusted driver. Maintain unprivileged execution, read-only root/source/job/fixtures, no network, dropped capabilities, no-new-privileges, CPU/memory/PID limits, and tmpfs constraints enforced by [`DockerSandbox`](../../src/corsair/adapters/sandboxing/docker.py). Development skills, if later needed, belong under `.agents/skills`; they are not runtime resources or image dependencies.
6. **Wire the established boundaries, not a second control plane.** Keep the narrow [`SandboxPort`](../../src/corsair/ports/sandboxing.py) implementation concrete: obtain `image_id`, detect unknown operations, and execute the `control` and `adversarial` roles. Keep verification in [`EvidenceVerifier`](../../src/corsair/steps/verification.py), identity construction in [`build_manifest`](../../src/corsair/steps/manifest.py), and pure disposition decisions in [`verdicts.py`](../../src/corsair/policies/verdicts.py). Add the actual adapter through explicit [`compose_worker_activities`](../../src/corsair/entrypoints/worker.py) composition only if it is implemented. Google ADK continues to run fresh, bounded role episodes and Temporal continues to coordinate durable work; do not add a registry, scheduler, repair loop, retry broker, string-to-object repair step, or custom agent protocol.
7. **Change only relevant native agent schemas.** If an extension changes a producer or auditor response shape, define the canonical Pydantic model once under `contracts/` and pass it directly as the ADK agent's native `output_schema` through the existing factories/adapter. [`AdkInference`](../../src/corsair/adapters/inference/adk.py) deliberately receives typed `ProducerDecision` or `AuditResult` data from bounded native episodes. A recipe-only or runtime-only extension should not invent a new model output schema.

## Runtime and configuration identity

The base-image digest in a Dockerfile is a supply-chain pin; it is **not** the runtime identity admitted for an evidence run. `DockerSandbox.image_id` resolves the configured local image tag to Docker's immutable local image ID. [`RunManifest.image_id`](../../src/corsair/contracts/sources.py) records that ID, and verification rejects a raw receipt whose `image_id` is missing, non-string, or different. A tag such as `corsair-python:0.1` selects an image; it is not sufficient evidence of which locally built image ran.

Rebuild after a driver or Dockerfile change. The same tag can resolve to a new Docker local image ID; the manifest distinguishes that run even if settings text is unchanged. [`Settings.identity`](../../src/corsair/settings.py) separately hashes configured image tag, Docker runtime, source/artifact roots, resource limits, queue, and model settings. The evidence intent also binds the recipe, submission, source artifact, budget, manifest configuration, image ID, and capability data. Do not reconcile, migrate, or reuse an operation across any changed recipe, source, image, settings, budget, model, native schema, or capability identity.

A framework may need an image dependency, but its setup must be deterministic and trusted inside the image/driver. Do not import a target framework into the development host, install target dependencies from the admitted tree at execution time, expose Docker sockets or credentials, or enable networking to make a test pass. The current risk assessment does not establish generic hostile-interpreter, kernel, daemon, or dependency-build integrity.

## Evidence, cleanup, and uncertainty requirements

A qualified recipe has separate offline, native, and composed evidence. Offline tests can validate schemas, admission, parser behavior, deterministic helpers, and failure gates. They cannot demonstrate real Docker isolation, a framework runtime, a model, or target execution. Fake `SandboxPort` tests are useful labelled unit tests but never native qualification.

Native evidence begins with the actual configured image ID before source preparation. The verifier records an immutable intent before side effects, rejects a prior unknown labelled container, executes the control before the adversarial role, validates driver/host exit-code agreement, source/submission/operation/role/container labels, relevant coverage, and image identity, then commits only complete evidence. Physical cleanup is a distinct gate: if control cleanup cannot be confirmed, no adversarial container may start. A missing driver record, malformed JUnit/coverage, mismatched identity, unexpected target exception, missing relevant coverage, unavailable dependency, cancellation, or unconfirmed cleanup must remain invalid/error/blocked uncertainty, never a violation or a negative result.

Keep the observation semantics in [`contracts/evidence.py`](../../src/corsair/contracts/evidence.py) and the conservative result policy in [`policies/verdicts.py`](../../src/corsair/policies/verdicts.py). A `VIOLATION` requires the exact trusted exploit assertion failure with a healthy control and exact target-line coverage in both runs; `PROPERTY_HELD` on the exploit input is `INCONCLUSIVE` for one session and counts toward `EXPLOIT_NOT_DEMONSTRATED` only with a second independent coverage-valid session. A fixed-source run is separate evidence and can report only whether that submitted demonstration is blocked while control behavior remains valid.

Never resubmit or delete an intent to obtain a clean result. An intent without a committed observation is uncertain even when no container is visible. Preserve its run/operation identity and inspect it; create a deliberately new run only after recording the prior uncertainty. [`EvidenceVerifier`](../../src/corsair/steps/verification.py) and the [CLI recovery guidance](../reference/cli.md#watching-and-recovery) enforce this distinction.

## Tests, frozen evaluations, and platform evidence

Add tests in the existing category that owns their primary behavior: unit contracts/policy, integration sandbox/source/image, workflow/replay, or security. Cover at least the control, adversarial disclosure/non-disclosure, unexpected exception, malformed/mismatched native record, identity mismatch, absent coverage, timeout, cancellation/infrastructure loss, source rejection, and cleanup-not-confirmed paths appropriate to the extension. A recipe that adds framework setup needs a real-image test demonstrating the intended API invocation, not a host import test.

Put executable evaluator behavior in the installed [`src/corsair/evaluation/`](../../src/corsair/evaluation/) package. Keep only declared datasets, fixtures, baselines, experiments, and evaluator documentation under [`evals/`](../../evals/). Dataset records digest the exact request and oracle bytes (for example, [`evals/datasets/dev.json`](../../evals/datasets/dev.json)); frozen fixture/oracle bytes are not a style-editing surface. The oracle remains local to the evaluator and must not enter source snapshots, agent prompts/tools, workflow inputs, request artifacts, or target containers. Preserve failed rows, unavailable results, invalid positives, and unknown model usage/cost in reports; missing telemetry is unknown, not zero.

Qualify isolated producer and auditor behavior independently before a finite composed evaluation. An isolated role check invokes the actual factory/native ADK runner against digest-verified input but does not run the target. A composed check requires a real worker, Temporal, reviewed Docker image, immutable artifacts, trusted observer, and external scorer. Neither small frozen cohorts nor scripted model doubles establish population accuracy or production readiness.

Run Linux amd64 and macOS arm64 evidence separately and report each host, daemon/runtime, image ID, commands, counts, skips, deselections, warnings, and unavailable gates. Current CI coverage is intentionally asymmetric: Linux amd64 has offline/package, Docker/Temporal native conformance, and durable workflow jobs; macOS arm64 has offline/package and Temporal. Hosted macOS does not substitute for physical Docker Desktop/Colima nested virtualization. Do not write a cross-platform claim until the relevant native gates have run on the claimed hosts.

## Current command surface

These are existing repository commands, not new extension subcommands. Run them from the repository root using the locked environment. Replace `/operator/settings.json` only with a deliberately selected private settings file; do not put credentials into it or command history. The examples use explicit settings, distinct IDs, and an explicit output path.

```bash
# Locked developer environment and all lint, formatting, type, and documentation gates.
nix develop
just sync
just check

# Offline contracts, source admission, evaluators, and installed-wheel resources.
just -- test -q -W error
just build

# Rebuild the reviewed native observer image, then execute real Docker/Temporal selection.
just images
CORSAIR_TEST_TEMPORAL=1 just -- test-docker -q -W error
just -- test-temporal -q -W error

# Explicit opt-in for the real 121-second Docker deadline regression.
CORSAIR_TEST_LONG_PROBE=1 just -- test-docker -q -W error \
  tests/integration/test_docker.py::test_real_docker_probe_deadline_can_exceed_120_seconds

# Isolated live role diagnostics: production factory/native runner, no target execution.
just -- eval-agent producer evals/datasets/producer-dev.json \
  --settings /operator/settings.json --repeats 3
just -- eval-agent auditor evals/datasets/auditor-dev.json \
  --settings /operator/settings.json --repeats 3

# Full native selection, including the explicitly configured live-provider smoke.
CORSAIR_LIVE_CONFIG=/operator/settings.json just -- test-all -q -W error
```

For a real native reference replay, inspect infrastructure first and use a unique reference identity. `verify` does not contact a model or Temporal and never produces a release-facing disposition:

```bash
EXTENSION_RUN_ID="extension-recipe-$(date +%s)"
uv run --locked corsair doctor --settings .state/settings.json
uv run --locked corsair verify evals/fixtures/case01/request.json \
  evals/fixtures/case01/submission.json \
  --run-id "${EXTENSION_RUN_ID}-reference" \
  --settings .state/settings.json
```

For a finite composed evaluation, start a separately configured worker as documented in the [configuration guide](configuration.md), then use a different explicit batch ID and report path:

```bash
EXTENSION_BATCH_ID="extension-eval-$(date +%s)"
uv run --locked --extra providers corsair eval evals/datasets/dev.json \
  --run-id "$EXTENSION_BATCH_ID" --repeats 3 --concurrency 2 \
  --output ".runs/evaluations/${EXTENSION_BATCH_ID}.json" \
  --settings .state/settings.json
```

If an extension proposal needs a command that is not listed in the [CLI reference](../reference/cli.md), treat the command name as a **proposal placeholder**, not documentation of an implementation. Do not write examples such as `corsair add-language`, `just test-framework`, or a fictional provider command. Add and test the concrete command first, or describe the intended operation in prose.

## Plan and pull-request acceptance checklist

Before requesting review, record the following in the active plan/PR and retain failed or unrun gates.

- [ ] **Scope and permissions:** The proposal names one recipe/property, claim scope, language, framework, target entry point, admitted source paths, target permissions, private/public fixtures, and all requested sandbox/image/runtime changes. It does not broaden authority by implication.
- [ ] **Canonical contracts:** The Pydantic models live once under `contracts/`, reject unknown fields, bind the finding/source/recipe safely, and are re-exported. A discriminated recipe union exists only if a concrete second recipe is implemented and tested; native ADK output schemas are added only when an actual role output shape changes.
- [ ] **Trusted runtime:** Framework/dependency setup is pinned and in the trusted image; no host target import or untrusted dependency installation occurs. The observer, JSON job schema, Docker restrictions, container labels, immutable cleanup identity, and raw native receipt have real implementations.
- [ ] **Identity:** The plan records source digest, recipe digest, settings/configuration identity, model identities, prompt/schema/capability digests, image tag and resolved Docker local image ID, runtime, budget, and host architecture. Changed identities receive new runs; old claims/results are replayed or explicitly retained as historical, not silently migrated or relabelled.
- [ ] **Evidence gates:** Tests cover source/permission rejection, control, adversarial behavior, coverage relevance, driver/JUnit/exit agreement, malformed records, image/operation/source/submission mismatch, timeout/cancellation, cleanup failure, and unknown operation. A real-image test validates actual framework setup where applicable.
- [ ] **Evaluation discipline:** Dataset request/oracle hashes are recorded; frozen oracles remain outside agents, tools, workflows, source snapshots, and containers. Isolated producer/auditor diagnostics, frozen composed evaluation, and external scoring are kept distinct. Candidate cases are not promoted by editing an oracle to make a result green.
- [ ] **Qualification record:** `just check`, focused tests, offline suite, wheel build/installed-resource check, affected Docker/Temporal/live checks, and each host platform result are recorded with command, result, count, skips/deselections, warnings, image ID, and elapsed time when material. Unavailable, failed, denied, interrupted, or unrun gates remain explicit.
- [ ] **Operations and delivery:** Logs contain only sanitized operational metadata, and unavailable model usage/tokens/cost remain unknown. The built wheel loads the driver, risk assessment, agent metadata, and instructions from package resources outside the checkout; development skills are excluded from runtime. No `.runs`, `.state`, credentials, raw evidence, private diagnostics, or generated caches enter source control.

See [testing](../development/testing.md), [agent evaluations](../agents/evaluations.md), [configuration identity](configuration.md#trusted-probe-deadline-and-image-identity), and the [current qualification record](../plans/README.md) for the state of the current tree. This guide describes the extension bar; it does not itself qualify a proposed language, framework, recipe, image, platform, model, or provider.
