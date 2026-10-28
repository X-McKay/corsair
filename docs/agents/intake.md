# Issue intake

Intake normalizes one issue, inspects an admitted local source snapshot, identifies execution requirements, and recommends an image from the currently available configured images. Standalone `intake` does not execute target code. Normal `investigate` embeds intake and starts recipe-free execution only after a supported decision; see [the workflow guide](../guides/investigations.md). Implementation and qualification results are tracked in [the implementation plan](../plans/active/PLAN-0131-intake-implementation.md).

## Submit an issue

Build the separate reviewed inspection image and run the ordinary worker with explicitly configured model and source settings:

```bash
just images-intake
uv run --locked corsair worker --settings /operator/settings.json
```

Submit either issue JSON or a qualified GitHub issue reference:

```bash
uv run --locked corsair intake --json /operator/issue.json \
  --source /operator/repository --settings /operator/settings.json --format json

uv run --locked corsair intake --issue 'OWNER/REPO#123' \
  --source /operator/repository --settings /operator/settings.json --format json
```

GitHub retrieval requires the repository's `OWNER/REPO` in `Settings.intake_github_repositories`. Credentials, if needed, use the worker's `GITHUB_TOKEN`. Only issue title/body are admitted; comments, attachments, pull requests and arbitrary linked URLs are excluded. The repository is supplied separately and must pass existing `source_root` and snapshot admission. Issue JSON cannot override source access.

The client waits for the recorded intake result. Model failures and uncertain inspection cleanup return explicit errors. A cancelled local wait does not prove workflow or container cancellation; immutable inspection-container ownership is reconciled before retry.

## Output and images

Canonical models live in [`contracts/intake.py`](../../src/corsair/contracts/intake.py). `IntakeProposal` contains the normalized issue, scope, surface, language, execution mode, requirement categories, suggested image, reason codes and grounded source locations. The trusted `IntakeResult` adds status, derived classification, identities, usage and a committed artifact reference.

The worker constructs a bounded inventory from configured Python/Node/Java observer images and optional operator-reviewed `intake_images`. It includes only locally present, permitted Linux images compatible with the Docker host architecture. Additional candidate metadata uses `ImageCandidate`: `requirements` describes capabilities the operator has reviewed for that image, not capabilities inferred from Docker labels. Adding an inventory entry does not implement or qualify a new execution route.

The packaged intake guidance separates issue meaning from environment support: scope, affected boundary and necessary capabilities are identified before choosing an image. An empty inventory does not make an understood security report out of scope or missing context. Requirements are empty when no extra capabilities are needed; `unknown` represents a concrete unresolved requirement, rather than speculative dependencies.

The agent has a bounded `compare_images` tool over that trusted episode inventory and a packaged `image-selection` skill. The native skill instructions are preloaded; optional refresh loaders expose only the reviewed packaged text. The tool compares source-derived language, mode and requirement categories, returning candidate matches and missing capabilities. It performs no Docker, network or target execution and cannot add inventory entries or grant permissions. The agent retains image choice, and trusted admission/rechecks remain authoritative. Actual model-requested tool calls and preloaded versus explicitly loaded skills are recorded separately.

Intake selects an exact inventory reference or null. `NO_COMPATIBLE_IMAGE` means the requirements are understood but none of the available images fits; `IMAGE_UNDETERMINED` means the image cannot be determined from available information. No image is pulled or built during intake, and repository Dockerfiles are never trusted or run.

A supported result means that an available image matches the identified capabilities and configured permissions. Intake v2 requires no recipe or investigation bindings. It does not authorize arbitrary execution or establish a security conclusion. Missing dependencies and requirements use categorical codes; unknown issue context remains `needs_input`.

The runner preloads bounded source files inside the inspection sandbox before the model episode, then exposes read-only source tools. Preloaded paths and model-requested reads are recorded separately. Cited grounded paths must have been read completely; a filename listing or explicitly truncated content does not qualify as inspection. The input packet identifies complete preloaded paths so the model can use those reads without repeating them.

Scanner envelopes may contain renamed fields, rich-text messages, scan summaries and repeated results. Intake must distinguish actual findings from scanner metadata and preserve the supplied finding details. Equivalent records can describe one issue; distinct or unresolved contradictory findings require input rather than silent first-record selection. An empty results collection does not establish repository safety. Scanner absolute paths are untrusted hints that must map unambiguously to inspected relative paths; both structured location fields use the canonical safe-path contract.

The inspection image is independent from the recommended image. Its source staging directory, beneath the configured artifact root, must be shared with the Docker daemon/VM. An unshared host path is an inspection failure. The reader has no shell tool, network, credentials, Docker socket, target imports or installation capability. This boundary does not establish generic hostile-host observation integrity.

## Evaluate intake

```bash
just -- eval-intake evals/datasets/intake-capabilities.json \
  --settings /operator/settings.json --repeats 1 \
  --output .runs/intake-evaluation/report.json
```

The eight recipe-free cases are candidate diagnostics pending human review. A separate `evals/datasets/intake-json.json` cohort exercises 32 scanner/JSON forms with optional normalization-detail checks; its shapes, revision history and limits are described in [the evaluator guide](../../evals/evaluators/intake.md). The original recipe-bound cohort at `evals/datasets/intake.json` is retained as a historical diagnostic with its original inputs and oracles. Inputs, source hashes, available-image inventories and external oracles are frozen. The scorer checks categories, requirement/reason sets, path/symbol associations, image membership and false-supported decisions. Arbitrary prose normalization fidelity still needs human review. Native schema tests, live-model accuracy, Docker conformance, Temporal replay and composed execution are separate gates.

The live-role evaluator uses frozen inventories without querying their availability on the evaluation host. It runs genuine ADK and the real inspection container, but does not establish composed admission or execute evidence observers. Raw reports remain private under `.runs/`; operational failures and invalid outputs remain in the full denominator. Native completion is requested as JSON against the canonical Pydantic schema. Invalid responses are rejected without string repair; bounded validation categories are recorded without response contents. Missing cost remains unknown.
