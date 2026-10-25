# First durable investigation

A durable investigation uses ordinary Temporal activities to coordinate bounded producer and outcome-blind auditor episodes with immutable artifacts. Unlike [reference replay](quickstart.md), it invokes the provider selected by the operator. It is a personal-use, component-scope pilot; a completed result is not a production, hostile-target, or population-accuracy claim.

Before starting, complete the no-model replay and retain its `.state/settings.json`. The fixture request remains `evals/fixtures/case01/request.json`: its `source` and `comparison` paths are resolved relative to that JSON, and the quickstart's `source_root` of `evals/fixtures/case01` admits those exact directories. For another request, choose the narrowest trusted `source_root` containing the request-relative source directory and review the [configuration guide](../guides/configuration.md) rather than copying a configuration schema into the request.

## Select the provider deliberately

Settings do not contain credentials. Before Terminal 2, explicitly select one supported connector in `.state/settings.json`:

- `models.connector` is either `gemini` or `litellm`.
- Set exact `models.producer` and `models.auditor` IDs for that connector. `models.api_base` is valid only with `litellm`; it must not contain credentials or query parameters.
- Supply the selected provider's credentials in **Terminal 2's worker environment only**, using the credential mechanism required by that provider. Do not put credentials in the settings file, request JSON, artifacts, logs, or client command line. Corsair does not auto-load a `.env` file or infer a provider from credentials.
- A `litellm` worker needs the optional `providers` extra. The command below includes it; the Gemini connector does not require LiteLLM model construction.

Do not start an investigation until a trusted Docker daemon is available, the reviewed image has been built with `just images`, and all worker/client processes can read the same configured artifact root.

## Start the three terminals

Run each command from the repository root after `nix develop` and `just sync`.

### Terminal 1: local Temporal service

```bash
temporal server start-dev --db-filename .state/temporal.db
```

This is local development persistence, not a host-loss recovery guarantee.

### Terminal 2: worker and provider credentials

First set the selected provider's credential variables in this terminal only. Then start the worker:

```bash
uv run --locked --extra providers corsair worker \
  --settings .state/settings.json --log-file .state/worker.log
```

The worker connects to the configured Temporal address, namespace, and task queue. It is the only process that constructs agents and reads provider credentials; the submitting client does not receive them through a request or CLI flag.

### Terminal 3: preflight and investigation

After the worker is running, check the real dependencies:

```bash
uv run --locked corsair doctor --format human --settings .state/settings.json
```

`doctor` checks configured source/artifact directories, Docker daemon/image/runtime, Temporal address/namespace, and task-queue pollers. It makes no model request and **does not verify provider credentials, model availability, prompt policy, or a future investigation result**. Stop and correct a nonzero report; a successful report is infrastructure readiness only.

With a ready report, submit the frozen request and wait for its actual result:

```bash
RUN_ID="case01-$(date +%s)"
uv run --locked corsair investigate \
  evals/fixtures/case01/request.json --run-id "$RUN_ID" --wait \
  --format human --settings .state/settings.json
```

The workflow writes immutable result and evidence artifacts to the shared artifact root. Ctrl-C detaches this client; it does not cancel the remote workflow. Use `corsair inspect "$RUN_ID" --online --watch` to follow a live workflow, or `corsair cancel "$RUN_ID"` to request cancellation, then inspect the final artifacts before claiming cleanup.

The recorded live model/Docker/Temporal batch is 2/3 and retains a safe-case second-round execution error; it does not establish population-level accuracy. See [the active safe-case issue](../plans/active/ISSUE-0010-live-safe-case-probe.md) before relying on this path beyond the stated pilot scope.

For supported platforms and Mac VM sharing, see the [development setup](../development/setup.md) and [platform reference](../reference/platforms.md). The [configuration guide](../guides/configuration.md) and [CLI reference](../reference/cli.md) are authoritative for evolving configuration and command behavior; current plans are collected in the [plans index](../plans/README.md).
