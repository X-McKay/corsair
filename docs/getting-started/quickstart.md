# Reference replay without a model

This quickstart exercises the trusted observer against the frozen `case01` request and submission. It needs a reachable Docker daemon and the reviewed local image, but makes **no model call and no Temporal request**. It returns a native observation rather than a release-facing security disposition.

Complete [installation](installation.md) first, including the macOS `DOCKER_HOST` and `TMPDIR` steps when applicable. Run every command below from the repository root.

## Prepare the fixture configuration

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
settings["source_root"] = "evals/fixtures/case01"
path.write_text(json.dumps(settings, indent=2) + "\n")
PY
just images
```

The request at `evals/fixtures/case01/request.json` declares `"path": "source"` and its fixed comparison as `"path": "comparison"`. Corsair resolves both paths **relative to that request JSON**, so this configuration admits `evals/fixtures/case01/source` and, when requested, `evals/fixtures/case01/comparison` under the narrow fixture root. For a different request, keep its declared source directories under the configured `source_root`; source admission rejects symlinks, replacement, and paths outside that root.

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

A Docker/image/runtime failure is operational, not evidence about the fixture. Build only the reviewed image with `just images` and resolve the daemon or VM problem rather than weakening policy. `doctor` is intentionally not part of this replay: it checks configured Docker **and** Temporal/worker-poller services, so it needs real services and does not prove model credentials.

Proceed to [your first durable investigation](first-project.md) only after this reference path works. See [development setup](../development/setup.md), [platform reference](../reference/platforms.md), [configuration guide](../guides/configuration.md), and the [CLI reference](../reference/cli.md) for authoritative detail. Current work and known limits are linked from the [plans index](../plans/README.md).
