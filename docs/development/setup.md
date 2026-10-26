# Development setup

This is the current local-work guide. It explains the locked toolchain and host prerequisites; exact command switches belong in the [CLI reference](../reference/cli.md), architecture in the [architecture overview](../architecture/overview.md), and current qualification or open work in [plans](../plans/README.md).

## Supported hosts and quick path

Corsair supports **Linux amd64** (`x86_64-linux`) and **Apple Silicon macOS** (`aarch64-darwin`) only. Windows, Linux ARM, and Intel macOS are outside the supported developer/CI matrix. Use a dedicated, disposable workspace for admitted source and native execution; Nix is a development shell, not a sandbox for an untrusted target.

Install Nix using the [official instructions](https://nix.dev/install-nix.html). Enable `nix-command` and `flakes`, or add `--extra-experimental-features 'nix-command flakes'` to Nix commands. From the repository root:

```bash
nix develop
just                         # Lists recipes; does not start work.
just sync
just check
just -- test -q -W error
just build
```

The `--` before a recipe separates Just's switches from literal recipe arguments. For example:

```bash
just -- verify evals/fixtures/case01/request.json evals/fixtures/case01/submission.json \
  --settings .state/settings.json --format human
just -- eval-agent auditor evals/datasets/auditor-dev.json \
  --settings .state/settings.json --repeats 3
```

Variadic recipes forward arguments literally rather than evaluating them as shell source. Run separate recipes as separate commands; do not append another recipe name after forwarded arguments. Recipes do not auto-load `.env`, create credentials, or retry a provider-policy block.

## Local environment and file lifecycle

`just sync` creates/updates the canonical root `.venv/`; do not keep using a dated task environment. Private/generated roots, local credentials, databases and delivery archives are Git-ignored. Ongoing settings and Temporal persistence belong under `.state/`, immutable evidence under `.runs/`, and disposable or explicitly retained investigation material under `.work/`. See [local files and retention](local-files.md) before cleanup or moving state.

## What is pinned—and what is not

`flake.lock` pins the Nixpkgs input. The shell provides Python 3.12, uv, Just, Bash, the Docker client, and the Temporal CLI. It sets `UV_PYTHON` to the Nix Python and `UV_PYTHON_DOWNLOADS=never`; `uv.lock` pins Python dependencies and artifacts. Python recipes use `uv --locked`, and CI enters the same shell with `--no-update-lock-file`.

This is reproducible tool and dependency selection, not a fully offline or bit-for-bit-hermetic application/image build. Initial setup may fetch the pinned Nix closure and locked Python artifacts. Docker daemon or VM configuration, the observer image build, local filesystem behavior, Temporal, and any provider response are external state. Interpret a passing command within those boundaries.

Update tools only in a deliberate change, not during ordinary development:

```bash
nix flake update nixpkgs
nix develop --command just sync check
nix develop --command just -- test -q -W error
```

Review the `flake.lock` diff, actual tool versions, and affected platform checks separately. Nix profiles and direnv are optional; they are not required for this path.

## Docker and native execution

The Nix shell supplies a Docker **client**, not a daemon. Start a reviewed Docker daemon on Linux or Docker Desktop/Colima's Linux VM on macOS. The Python Docker SDK reads `DOCKER_HOST`, not the Docker CLI's selected context. If the selected trusted local context is not already visible to the SDK, expose its socket explicitly:

```bash
export DOCKER_HOST="$(docker context inspect --format '{{.Endpoints.docker.Host}}')"
docker info
just images
```

A rootless Linux daemon can likewise be selected with its actual `DOCKER_HOST` socket. Only use a context you trust: it decides where admitted source and containers run. Keep source and staging directories under paths shared with Docker Desktop or Colima. Do not compensate for an unavailable daemon by changing runtime, mount, network, resource, or cleanup policy.

On macOS, Colima commonly cannot see the default `/private/var/folders` temporary tree. Native observer staging uses Python's temporary-directory API, so place it under the reviewed checkout before Docker-backed work:

```bash
mkdir -p .work/tmp
export TMPDIR="$PWD/.work/tmp"
just images
```

For pytest, also set a shared base directory when necessary:

```bash
CORSAIR_TEST_TEMPORAL=1 just -- test-docker -q -W error \
  --basetemp="$PWD/.work/pytest-tmp"
```

`TMPDIR` and `--basetemp` select shared filesystem locations; they do not select a weaker observer or sandbox. The [platform reference](../reference/platforms.md) records the capability-based source-admission requirements and the physical-Mac Docker boundary.

## Real services and settings

Offline tests need no Docker daemon, Temporal service, or model credentials. Docker and Temporal tests have explicit gates; see [testing](testing.md). For a real workflow, use one operator-controlled settings file for the client and worker, start the Temporal service and worker separately, and run `corsair doctor` before submission. Settings select local paths, Docker/Temporal values, image/runtime, budgets, and models; their exact fields remain defined by [`src/corsair/settings.py`](../../src/corsair/settings.py).

Credentials belong only in the worker environment. Do not put tokens, passwords, query-string credentials, raw provider output, `.state/`, `.work/`, or `.runs/` into the repository. A live-provider test additionally requires an operator-supplied `CORSAIR_LIVE_CONFIG`; its absence is a skip, not a credential fallback or a qualified live result.

## Further development guidance

- [Conventions](conventions.md) explains package ownership, native SDK boundaries, immutable evidence, and style rules.
- [Testing](testing.md) maps each Just recipe to its prerequisites and qualification scope.
- [Debugging](debugging.md) preserves safe logs, receipts, and security gates while investigating failures.
- [Contributing](contributing.md) defines the bounded implementation, test, cleanup, retest, and packaging sequence.
- [Plans](../plans/README.md) separates active decisions from archived historical records.

The repository has no project-wide license grant at present; [LICENSE](../../LICENSE) records that status.
