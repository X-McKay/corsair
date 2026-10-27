# Configuration guide

Corsair settings select the operator-owned execution boundary: the admitted local source root, immutable artifact location, Docker evidence environment, Temporal namespace/queue, and the two role models. They do not carry finding inputs, oracle labels, prompts, source credentials, or provider credentials. The canonical field list, defaults, and validation rules are in the [configuration reference](../reference/configuration.md); do not maintain a second schema here.

## Start from the reviewed example

From the repository root, create a private local settings file and edit it before admitting a case:

```bash
mkdir -p .state
cp deploy/settings.example.json .state/settings.json
```

Keep `.state/settings.json` and `.runs/` out of source control. Validate infrastructure after every meaningful settings change:

```bash
uv run --locked corsair doctor --settings .state/settings.json
```

`doctor` checks readable source/artifact paths, the configured Docker daemon/image/runtime, Temporal namespace, and task-queue pollers. It does not make a model call or verify provider credentials, so a ready result is infrastructure readiness—not a provider or evidence qualification.

## Choose paths and durable identities deliberately

Set `source_root` to the narrowest **absolute** directory containing sources that may be admitted. Source admission is local only: it snapshots an operator-selected filesystem path and does not implement remote SCM checkout. A request's source paths are resolved relative to the request JSON file by the CLI loader; they still must end up under the configured admission root.

Set `artifact_root` to one location visible to the worker and every client that needs offline `inspect` or rescoring. Artifacts and committed result receipts are immutable, but a local path is not durable merely because it is immutable. Use a shared/backed-up filesystem before depending on host-loss recovery; Temporal history cannot recreate an unrelated artifact filesystem.

`temporal_address`, `temporal_namespace`, and `task_queue` must name the same service/namespace/queue for client and worker. A missing poller is an operational block, not an invitation to submit work to a different queue. The current settings model carries an address and namespace only; it does not configure Temporal Cloud authentication, mTLS certificates, or an application-specific TLS transport. Do not place credentials in the address.

Retain the reviewed `image` and Docker `runtime` unless a change has its own native qualification. The remaining resource settings are operator limits for the Docker observer and source admission, not model-editable inputs. A changed image or settings identity changes the context recorded for a run.

## Trusted probe deadline and image identity

`Budget.probe_timeout_seconds` is the one validated wall-clock deadline for each
trusted container role. `DockerSandbox` starts that deadline with the container,
stops the immutable labeled container on expiry, and owns its cleanup confirmation.
The in-container driver deliberately has no independent pytest target-execution
cap. After pytest exits it reads the target module's executed lines from the coverage
data in its own process, still under the outer container deadline.

The trusted driver is copied into the reviewed Docker image. After this driver or
Dockerfile changes, the parent must rebuild from this worktree with `just images`
before running a real Docker regression or native replay. Rebuilding the same image
tag after a driver or Dockerfile change produces a new immutable image ID recorded in
each run manifest. If the settings JSON is unchanged, `Settings.identity` remains the
same because it hashes settings, not image bytes; the manifest image ID distinguishes
the changed runtime. Changing a recipe or probe budget is likewise a new evidence
identity through the recipe and budget digests in the execution intent. Changing a
settings field such as `image` or `runtime` changes `Settings.identity`. Do not
reconcile or reuse an operation across
any changed recipe, budget, settings, or image-runtime identity.

## Configure models without embedding secrets

The `models` object selects one `connector`, the producer and auditor model names, an optional request timeout, and narrowly allowlisted generation controls.

- With `connector: "gemini"`, model names are passed to Google ADK as native model IDs. `api_base` must be absent.
- With `connector: "litellm"`, install/run with the optional provider dependencies and choose model names understood by ADK's native LiteLLM path. `api_base`, if used, must be an `http` or `https` endpoint without user info, query parameters, or fragments. It is an endpoint selector, not a place for a key.
- `extra_body` accepts only `reasoning`, `reasoning_effort`, or `thinking`; it cannot add headers, credentials, tools, or arbitrary provider controls. The adapter sets LiteLLM retries to zero.
- `decoding` optionally sets `temperature`, `top_p` and `seed`, either once for both roles (`{"temperature": 0, "seed": 7}`) or per role (`{"producer": {…}, "auditor": {…}}`). Unset parameters are not sent, so the server's defaults apply. Any set parameter changes `Settings.identity`; see the [`Decoding` reference](../reference/configuration.md#decoding).

Provide the selected provider's credentials only in the **worker process environment** (for example, the local shell or a host secret mechanism that launches the worker). Never put them in settings, request JSON, reports, artifacts, logs, endpoint URLs, or CLI arguments. Start a provider-enabled worker separately from clients:

```bash
uv run --locked --extra providers corsair worker \
  --settings .state/settings.json \
  --log-level INFO --log-file .state/worker.log
```

The client that submits or inspects a workflow does not receive provider credentials through the request or settings file. Sanitized logs are still operationally sensitive; keep their directory restricted.

## Make changes auditable

Treat a model, endpoint, image, root path, runtime, queue, or budget change as a new operator decision. `Settings.identity` is the digest of those settings only; the run manifest separately fingerprints each role's metadata, prompt, and native output schema. Therefore a producer decision-schema change alters the producer capability fingerprint without pretending that unchanged settings have a new settings digest. Re-run `doctor`, run native reference replay before changing evidence environment behavior, and qualify prompt/model changes on their frozen role evaluation before a finite composed batch. Do not compensate for a provider denial, timeout, or unavailable Docker dependency by adding credentials to configuration, broadening paths, enabling target networking, or silently switching providers.

For operating sequence and recovery, see the [pilot runbook](../operations/runbooks/pilot.md). For scoped outstanding work and known limits, see the [current plans](../plans/README.md).
