# Extending Corsair safely

Corsair extends one bounded operator-owned recipe at a time. Start from the [risk assessment](../../src/corsair/policies/risk.md), [security architecture](../architecture/security.md), [language recipes](languages.md), [testing guide](../development/testing.md), and the active [PLAN-0127 record](../plans/archive/plans/PLAN-0127-outcomes-node-java.md). That record, rather than this guide, reports commands actually run and any remaining gates.

An extension is evaluated only for the exact source, recipe, runtime image, configuration, model, and host boundary in its evidence. A healthy control or a held adversarial observation alone does not complete an assessment.

## Current recipe surface

The canonical `Recipe` union in [`contracts/sources.py`](../../src/corsair/contracts/sources.py) contains `PythonRecipe`, `JavaScriptRecipe`, and `JavaRecipe`.

| Family | Implemented bounded ABI | Observer status |
| --- | --- | --- |
| Python | Standard-library public callable in `.py`; one JSON payload parameter and operator-fixed kwargs. | Existing Python route. |
| Node | Dependency-free named ESM export in `.mjs`; one JSON payload inserted into positional arguments. `allowed_exceptions` is exactly `Error`, `TypeError`, or `RangeError`. | Checked-in `node:test` observer with native JUnit and LCOV reporting. |
| Java | Public static `String` method with `String` arguments in matching `.java`/public class; inserted payload is a string and exception names are qualified. | Checked-in pinned JDK/JUnit Platform/JaCoCo/Jackson observer. |

The Node and Java observers are implemented candidate routes, not final language qualification. They admit no target dependency installation, target build scripts, or annotation processing. A Java target is compiled only by the reviewed observer with `javac -proc:none`.

## A bounded extension change

1. State one observable property: source entry point, recipe, public control, adversarial pair, permitted exceptions, image, scope, source limits, and host boundary.
2. Change the canonical Pydantic contract only for real behavior. Keep frozen, extra-forbidden data, normalized paths, bounded values, and operator-fixed values; do not create a registry or duplicate driver schema.
3. Preserve source admission and its immutable snapshot. A request never grants a model, image, or target extra source access.
4. Implement one recipe-specific trusted observer that receives operator-created data and emits one strict native receipt. Models never author tests, assertions, build commands, or evidence conclusions.
5. Put only observer runtime dependencies in the image. The current Java observer pins its own JDK, JUnit Platform, JaCoCo, and Jackson dependencies; this does not admit target dependencies.
6. Reuse existing boundaries: `SandboxPort` selects the recipe image, `EvidenceVerifier` validates receipt/coverage/cleanup, the manifest binds identity, and policy derives conservative results.
7. Run affected offline, native-image, Temporal/replay, isolated-role, and finite composed checks with their explicit prerequisites. Preserve failures and unrun gates in the current plan.

## Identity and paired outcomes

`Settings.image_for_recipe()` chooses the configured recipe tag. `DockerSandbox.image_id_for(recipe)` resolves the tag to the local immutable image ID; the manifest and native receipt bind that ID. Settings, recipe, source, budget, prompt/schema, capability, model, image ID, or host changes require a new run.

A `corsair.result/2` assessment outcome is complete only with `execution_status: COMPLETED`, valid native receipt/coverage, confirmed cleanup, and accepted independent audit:

- `DEMONSTRATED` additionally requires a healthy control and a valid actually executed adversarial disclosure.
- `NOT_DEMONSTRATED` additionally requires the diverse finite protocol to complete with valid held adversarial attempts. A repeated candidate, unavailable/error attempt, or rejected audit remains unresolved rather than completing the negative outcome.

The workflow sends producers only mechanical follow-up information; it does not return evidence labels in feedback. The scorer revalidates the immutable committed final result, not an independently supplied claim. Legacy `corsair.result/1` records and frozen legacy cohorts retain their original bytes and labels.

## Current task and diagnostic surface

```bash
# Build all reviewed observer images.
just images

# Build one image with an optional literal tag.
just images-python 'corsair-python:0.1'
just images-node 'corsair-node:review-candidate'
just images-java 'corsair-java:review-candidate'

# Baseline Python infrastructure preflight only.
uv run --locked corsair doctor --settings .state/settings.json
```

`just images` aggregates `images-python`, `images-node`, and `images-java`. `doctor` checks baseline Python infrastructure; it does not select or qualify a recipe image, execute a target, test provider access, or validate evidence.

## Review checklist

Retain the exact source/recipe/image/configuration identities; frozen request and oracle hashes; control/adversarial/invalid/cleanup evidence; relevant native reports and coverage; independent audit; replay and consumer results; and explicit host/service/provider prerequisites. The [PLAN-0127 record](../plans/archive/plans/PLAN-0127-outcomes-node-java.md) must retain actual results, failures, and pending requalification without changing historical records.
