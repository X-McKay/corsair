# Reference replay without a model

This quickstart exercises the trusted observer against the frozen `case01` request and submission. It needs a reachable Docker daemon and the reviewed local image, but makes **no model call** and needs no provider credentials. It returns a native observation rather than a release-facing security disposition.

Complete [installation](installation.md) first, including the macOS `DOCKER_HOST` and `TMPDIR` steps when applicable. Run every command below from the repository root.

## Run it with two commands

```bash
nix develop -c just sync images
nix develop -c just demo
```

`just demo` runs four steps, each also available as its own recipe:

1. `just settings-init` copies `deploy/settings.example.json` to `.state/settings.json` once, setting `source_root` to the absolute repository root. It never overwrites an existing file, so later edits are yours.
2. `just temporal-up` starts a background `temporal server start-dev` with its pid, log and database under `.state/`. A second call reports the running server. If the configured local port (7233 by default) cannot be bound, or something else already answers on it (for example a NAT rule forwarding `localhost:7233` to another Temporal), it picks a free port and records it as `temporal_address` in `.state/settings.json`; otherwise the defaults stay. It refuses a non-local `temporal_address`.
3. `corsair doctor` checks the source and artifact roots, Docker, the image and runtime, and the Temporal namespace. Before a worker exists the `worker_pollers` check is `warn`, which the demo accepts; any other failing check stops it.
4. `corsair verify` runs the case01 native observation described below.

Stop the background server with `just temporal-down`, which signals only the process it started, waits until no member of its process group remains, and removes the pid file. `just worker-up` and `just worker-down` do the same for `corsair worker` when you continue to the [first durable investigation](first-project.md).

## What the recipes do by hand

The same configuration, without Just:

```bash
nix develop
just sync
mkdir -p .state
cp deploy/settings.example.json .state/settings.json
python - <<'PY'
import json
from pathlib import Path

path = Path(".state/settings.json")
settings = json.loads(path.read_text())
settings["source_root"] = str(Path.cwd())
path.write_text(json.dumps(settings, indent=2) + "\n")
PY
just images
```

The request at `evals/fixtures/case01/request.json` declares `"path": "source"` and its fixed comparison as `"path": "comparison"`. Corsair resolves both paths **relative to that request JSON**, so this configuration admits `evals/fixtures/case01/source` and, when requested, `evals/fixtures/case01/comparison` under the repository root. Narrow `source_root` to the smallest directory that holds authorized source before admitting anything other than the frozen fixtures. For a different request, keep its declared source directories under the configured `source_root`; source admission rejects symlinks, replacement, and paths outside that root.

## Run the native observation

```bash
uv run --locked corsair --format human verify \
  evals/fixtures/case01/request.json \
  evals/fixtures/case01/submission.json \
  --settings .state/settings.json
```

`verify` snapshots the admitted source, runs the fixture's control and adversarial payloads in fresh offline Docker containers, and records the native observation in the configured artifact root. It does not start a worker, contact Temporal, use provider credentials, or decide a durable investigation result. Exit status `0` means the reference execution was healthy; inspect the observation itself before drawing any conclusion.

For machine-readable output, JSON is the complete stdout stream while operational diagnostics remain on stderr:

```bash
set -o pipefail
uv run --locked corsair --format json verify \
  evals/fixtures/case01/request.json \
  evals/fixtures/case01/submission.json \
  --settings .state/settings.json | python -m json.tool
```

A Docker/image/runtime failure is operational, not evidence about the fixture. Build only the reviewed image with `just images` and resolve the daemon or VM problem rather than weakening policy. `verify` itself needs no Temporal service; the demo starts one only so that `doctor` can check the whole local stack. `doctor` does not prove model credentials.

Proceed to [your first durable investigation](first-project.md) only after this reference path works. See [development setup](../development/setup.md), [platform reference](../reference/platforms.md), [configuration guide](../guides/configuration.md), and the [CLI reference](../reference/cli.md) for authoritative detail. Current work and known limits are linked from the [plans index](../plans/README.md).
