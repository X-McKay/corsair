# Deployment guide

Corsair is a personal-use, disposable-host pilot—not a hosted service or a production deployment recipe. The application is run as a local Python client and Temporal worker. `just images` builds the reviewed Docker image used for native target evidence; the repository does **not** provide a containerized Corsair application/worker image, an HTTP server, or a deployment manifest.

## Supported host boundary

Use a dedicated disposable Linux amd64 host for a pilot. Apple Silicon macOS is supported for the locked local workflow when Docker Desktop or Colima supplies a trusted Linux VM; it is not a substitute for an independently reviewed service deployment. Linux ARM, Intel macOS, and Windows are outside the supported matrix. See [supported platforms](../reference/platforms.md) and [development setup](../development/setup.md).

Do not admit third-party source on a workstation or server holding production workloads, unrelated Docker access, or credentials. The worker may read provider credentials from its own environment; target containers must never receive those credentials, the Docker socket, or arbitrary host mounts.

## Establish the local pilot

From the repository root, use the locked toolchain, validate the checkout, and build the reviewed evidence image:

```bash
nix develop
just sync
just check
just test
just images

mkdir -p .state
cp deploy/settings.example.json .state/settings.json
```

Before starting services, set a narrow absolute source root and a shared/backed-up artifact root in the local settings file. Keep the configured image and runtime under review. The [configuration guide](configuration.md) explains those decisions; the [configuration reference](../reference/configuration.md) is the exact settings authority.

For a local development Temporal service, start it in one terminal:

```bash
temporal server start-dev --db-filename .state/temporal.db
```

Then launch the worker in another terminal with provider credentials available only in that worker environment:

```bash
uv run --locked --extra providers corsair worker \
  --settings .state/settings.json \
  --log-level INFO --log-file .state/worker.log
```

The development server's SQLite persistence is local development infrastructure only. Before asserting recovery across host loss, use a shared/backed-up artifact filesystem and a reviewed durable Temporal deployment. The current CLI can connect to the configured address and namespace, but it has no settings or commands for Temporal Cloud authentication, API-key authentication, client certificates, or mTLS. Do not describe this setup as a Temporal Cloud or TLS-enabled deployment without implemented, reviewed support.

Finally, check actual dependencies from a client terminal:

```bash
uv run --locked corsair doctor --settings .state/settings.json
```

A ready report confirms Docker, paths, Temporal namespace, and worker pollers; it neither tests provider credentials nor proves that a future investigation will succeed.

## Preserve native isolation and permissions

The Docker daemon/socket is a high-trust host capability. Point the Python Docker SDK only at a trusted local/rootless socket using the operator's environment, and verify it with `docker info`. On macOS, the SDK reads `DOCKER_HOST`, not merely the Docker CLI context; keep source/artifact staging and `TMPDIR` inside a reviewed VM-shared directory. Do not make a daemon reachable by broadening socket permissions just to pass a check.

The reviewed sandbox image, runtime, no-network policy, read-only/drop-capability/resource/cleanup controls, and native source-admission checks are part of the evidence boundary. Do not mount the Docker socket into a target container, pass source-control or cloud credentials through source/configuration, enable target networking, use an unreviewed image tag, or relax limits to obtain a pass. Missing Docker/runtime capabilities, unavailable shared mounts, or source-admission rejection are operational failures to correct outside the target.

Use explicit cancellation and inspection during shutdown. `SIGTERM` gives the worker up to 45 seconds for native graceful shutdown, but neither that timeout nor a cancellation request proves that target cleanup completed. Follow a cancellation with online inspection, then inspect the committed artifact receipt. The [pilot runbook](../operations/runbooks/pilot.md) has the exact recovery sequence.

For current pilot limitations and deferred deployment work, see the [current plans](../plans/README.md).
