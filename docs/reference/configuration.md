# Configuration reference

Corsair's operator configuration is the immutable Pydantic `Settings` model in [`src/corsair/settings.py`](../../src/corsair/settings.py). This page is a field guide, not a second configuration schema: validate JSON with the installed package and consult that model for canonical validation. Credentials are intentionally absent.

```bash
mkdir -p .state
cp deploy/settings.example.json .state/settings.json
uv run --locked corsair doctor --settings .state/settings.json
```

`load_settings(path)` validates supplied JSON as `Settings`; without a path it returns `Settings()` defaults. It does not merge environment variables into settings. The checked-in example intentionally contains baseline fields; omitted fields retain their validated defaults.

## `Settings`

Fields without a range below are model-validated strings; adapter behavior is owned by the consuming implementation.

| Field | Default | Operational use |
| --- | --- | --- |
| `artifact_root` | `.runs` | Local immutable artifact-store path. |
| `source_root` | `.` | Bounds local source admission. |
| `temporal_address` | `localhost:7233` | Temporal SDK connection address. |
| `temporal_namespace` | `default` | Temporal namespace. |
| `task_queue` | `corsair` | Queue for workflow start and worker polling. |
| `image` | `corsair-python:0.1` | Python recipe image. |
| `node_image` | `corsair-node:0.1` | Node `.mjs` ESM/JSON recipe image. |
| `java_image` | `corsair-java:0.1` | Java static `String`/`String` recipe image. |
| `runtime` | `runc` | Docker runtime name. |
| `memory_limit` | `512m` | Docker memory-limit string. |
| `nano_cpus` | `1000000000` | Integer at least `100000000`. |
| `pids_limit` | `64` | Integer from `16` through `512`. |
| `source_limit_bytes` | `8388608` | Integer from `1024` through `33554432`. |
| `source_limit_files` | `1000` | Integer from `1` through `10000`. |
| `models` | default `ModelSettings` | Nested model-selection configuration. |

`Settings.image_for_recipe(recipe)` selects `image`, `node_image`, or `java_image` by canonical recipe type. `Settings.identity` is the SHA-256 digest of canonical validated settings JSON. A tag selects a local image; `DockerSandbox.image_id_for()` resolves that tag to the immutable local image ID recorded in the manifest and checked against native receipts. A tag or settings digest is not a qualification result.

## `ModelSettings`

| Field | Default | Validation / use |
| --- | --- | --- |
| `connector` | `gemini` | Exactly `gemini` or `litellm`. |
| `producer` | `gemini-2.5-flash` | Producer model name. |
| `auditor` | `gemini-2.5-flash` | Auditor model name. |
| `api_base` | `null` | Optional HTTP(S) endpoint with hostname; only with `litellm`, without user info, query, or fragment. |
| `request_timeout_seconds` | `120` | Integer from `1` through `300`; passed to LiteLLM only when selected. |
| `extra_body` | `{}` | Mapping limited to `reasoning`, `reasoning_effort`, and `thinking`. |

Credentials stay only in the worker process environment. The LiteLLM adapter receives selected model, allowlisted endpoint, timeout, and `extra_body`; Gemini names use the native ADK path.

## Observer image tasks and diagnostics

```bash
# Build all reviewed observer images.
just images

# Build an individual image with an optional literal tag.
just images-python 'corsair-python:0.1'
just images-node 'corsair-node:review-candidate'
just images-java 'corsair-java:review-candidate'
```

`images` depends on `images-python`, `images-node`, and `images-java`. The Node observer is the dependency-free `.mjs` ESM/JSON route using native `node:test` JUnit/LCOV reporting. The Java observer is the static `String`/`String` route with pinned JDK/JUnit Platform/JaCoCo/Jackson observer dependencies; target dependencies, build scripts, and annotation processing remain outside the recipe.

`corsair doctor --settings PATH` is an infrastructure preflight for source/artifact paths, Docker, configured runtime, **the baseline Python `image` only**, Temporal namespace, and task-queue pollers. It does not build images, resolve a Node/Java recipe image, call a model, validate provider credentials, execute target source, validate native evidence, or qualify a recipe.

## Alignment and status

Worker and client must agree on `temporal_address`, `temporal_namespace`, `task_queue`, and access to the same `artifact_root`. Configure `source_root` narrowly enough to contain each requested local source tree. Select a reviewed image for the concrete recipe and an available Docker runtime.

Changing settings, recipe, budget, capability, prompt/schema, source, model, resolved image ID, or host requires a new run rather than reconciliation. For actual Node/Java native and composed results, remaining gates, and qualification status, use [PLAN-0127](../plans/archive/plans/PLAN-0127-outcomes-node-java.md). See [language recipes](../guides/languages.md) for request shapes and [schemas](schemas.md) for canonical contract fields.
