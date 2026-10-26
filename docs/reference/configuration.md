# Configuration reference

Corsair's operator configuration is the immutable Pydantic `Settings` model in [`src/corsair/settings.py`](../../src/corsair/settings.py). This page is a field guide, not a second configuration schema: validate the JSON with the installed package and consult that model for the canonical definition. Credentials are intentionally absent from these models.

Use an explicit JSON file when operating the worker or CLI:

```bash
mkdir -p .state
cp deploy/settings.example.json .state/settings.json
uv run --locked corsair doctor --settings .state/settings.json
```

`load_settings(path)` reads the given JSON file and validates it as `Settings`; when called with no path it returns `Settings()` defaults. It does not merge environment variables into settings. Use repository-root-relative commands such as those above.

## `Settings`

All contracts are frozen, reject unknown fields, and disallow non-finite floats. Fields without an explicit range below are validated as strings by the model; their operational interpretation belongs to the adapter that consumes them.

| Field | Default | Validation / operational use |
| --- | --- | --- |
| `artifact_root` | `.runs` | String path for the local immutable artifact store. Every worker and client that must inspect/reconcile results needs the same durable/shared location. |
| `source_root` | `.` | String path that bounds local source admission. The admission layer requires a real non-symlink directory and rejects source paths outside it or containing symlinks. Use the narrowest practical absolute directory. |
| `temporal_address` | `localhost:7233` | Temporal SDK connection address. |
| `temporal_namespace` | `default` | Temporal namespace passed to the SDK client. |
| `task_queue` | `corsair` | Queue used when workflows are started and when the worker polls. |
| `image` | `corsair-python:0.1` | Docker image reference used by the trusted sandbox adapter. |
| `runtime` | `runc` | Docker runtime name used by the sandbox adapter. |
| `memory_limit` | `512m` | Docker memory-limit string. |
| `nano_cpus` | `1000000000` | Integer, at least `100000000`. |
| `pids_limit` | `64` | Integer from `16` through `512`. |
| `source_limit_bytes` | `8388608` | Integer from `1024` through `33554432`; bounds admitted source bytes. |
| `source_limit_files` | `1000` | Integer from `1` through `10000`; bounds admitted source files. |
| `models` | a default `ModelSettings` | Nested model-selection configuration below. |

`Settings.identity` is a SHA-256 digest of the canonical JSON representation of the validated settings. It is used as configuration identity in run metadata; it is not a secret store.

## `ModelSettings`

| Field | Default | Validation / use |
| --- | --- | --- |
| `connector` | `gemini` | Exactly `gemini` or `litellm`. |
| `producer` | `gemini-2.5-flash` | String model name for the producer. |
| `auditor` | `gemini-2.5-flash` | String model name for the auditor. |
| `api_base` | `null` | Optional HTTP(S) endpoint with a hostname. It must contain no username, password, query, or fragment. It is valid only with `connector: "litellm"`; Gemini rejects a configured value. |
| `request_timeout_seconds` | `120` | Integer from `1` through `300`; passed to LiteLLM when that connector is selected, lowered to the model episode bound when it is longer (see [time bounds](#time-bounds)). |
| `extra_body` | `{}` | Mapping limited to the keys `reasoning`, `reasoning_effort`, and `thinking`. Other generation, credential, and tool-override keys are rejected. |

The LiteLLM adapter receives only the selected model, allowlisted `api_base`, timeout, and `extra_body`; it explicitly uses zero LiteLLM retries. Gemini model names are resolved through the native ADK path. Neither route accepts provider credentials from `Settings`.

## Time bounds

Every elapsed-time limit of an investigation is derived in one pure module, [`policies/time_bounds.py`](../../src/corsair/policies/time_bounds.py). The workflow schedules activities with it, and the inference adapter sizes the model episode and each provider request from the window of the activity that runs it, so the limits nest instead of racing:

```text
provider request <= model episode < activity window <= remaining investigation time
```

| Bound | Default | Derivation and owner |
| --- | --- | --- |
| Investigation action deadline | `900` s | `Budget.max_elapsed_seconds`. The workflow clamps every activity it schedules to the time remaining before it. |
| Workflow execution timeout | `1020` s | `max_elapsed_seconds + 120`, set by the API and by the batch workflow for each child, so the final record fits after the deadline. |
| `corsair.prepare` activity | `120` s | Fixed, clamped to the deadline. |
| `corsair.produce` activity | `300` s | `min(300, max_elapsed_seconds - elapsed)`, clamped to the deadline. |
| `corsair.audit` activity | `180` s | Fixed, clamped to the deadline. |
| Model episode (producer, auditor) | `285` s, `165` s | The activity window minus a reserve of 10 % (at most 15 s). The window is read from the started activity's scheduled timeouts, less any time it waited in the queue. The episode ends with the operational `episode_timeout` gate before the activity's own bound can fire. |
| Provider request | `120` s | `min(request_timeout_seconds, episode)`. Applied to the LiteLLM connector; the native Gemini route is bounded by the episode only. With the live `300` s setting the effective request bound is `285` s for the producer and `165` s for the auditor. |
| `corsair.evidence` activity | `105` s | `2 * probe_timeout_seconds + 45`: two sandboxed roles, each bounded by `probe_timeout_seconds` in the Docker adapter, plus container overhead. |
| `corsair.record` activity | `30` s per attempt | Three attempts inside a `90` s schedule-to-close bound (`bounded-finalization-v1`). |
| Activity heartbeat timeout | `15` s | `min(15, activity)`. Model episodes heartbeat every 2 s; evidence heartbeats from the Docker wait loop. |

Isolated agent evaluation runs an episode without an activity; it uses the window a fresh investigation would grant the role (`min(300, max_elapsed_seconds)` for the producer, `180` s for the auditor), so its episodes are bounded as in production. The activity values are recorded in workflow histories: changing one changes scheduled activity options and needs a `workflow.patched` gate and a replay test. There is no per-request knob for a model slower than its activity window; such a run stops with `episode_timeout` (see [troubleshooting](../operations/troubleshooting.md#a-model-episode-stops-with-episode_timeout)).

## Worker credentials and process boundaries

Provider credentials belong in the **worker process environment** used to run `corsair worker`. They do not belong in `Settings`, `ModelSettings`, request JSON, source snapshots, manifests, artifacts, or API arguments. Do not place credentials in `api_base`: its validator rejects endpoint user info, queries, and fragments.

The configuration loader does not provide an environment-variable override mechanism for settings. Configure the selected provider through its supported worker-environment mechanism, without recording a real credential or endpoint in project files. A client that only connects to Temporal uses `Settings` to select the address, namespace, and queue; it does not receive credentials through the investigation request.

Keep provider credentials and the Docker socket outside target containers. The target sandbox uses the configured image and runtime, while credentials remain on the worker side.

## Alignment checks

Before submission, make these values intentionally consistent:

- **Worker and client:** `temporal_address`, `temporal_namespace`, `task_queue`, and access to the same `artifact_root`.
- **Source admission:** a narrow `source_root` that contains the local source tree named by each request; a request path is not authority to read elsewhere on the host.
- **Sandbox:** a reviewed image and available Docker runtime. `doctor` reports whether the configured daemon, image, runtime, directories, namespace, and task-queue pollers are reachable; it does not start them, send a model request, or validate provider credentials.

Platform support is limited to the qualified developer targets described in the [platform reference](platforms.md). The development shell and Python dependencies are pinned, but this is not a claim of a fully hermetic runtime; see [development setup](../development/setup.md).

For request paths and native Temporal use, see the [Python API reference](api.md). For the models represented in JSON, see [domain schemas](schemas.md). Current configuration-related work is linked from [current plans](../plans/README.md).
