# Reproducible development on macOS and Linux

Install Nix using the [official platform instructions](https://nix.dev/install-nix.html). Enable `nix-command` and `flakes` in your Nix configuration, or append `--extra-experimental-features 'nix-command flakes'` to the commands below. Then, from a checkout:

```bash
nix develop
just                     # List the documented tasks; does not start work.
just sync check
just -- test -q -W error
just build
```

`flake.lock` pins one Nixpkgs revision and its content hash. The development shell provides Python 3.12, uv, Just, Bash, the Docker client and Temporal CLI on `aarch64-darwin` and `x86_64-linux` (Apple Silicon macOS and amd64 Linux only). No flake utility framework, additional lock translator or compiler development environment is required. `UV_PYTHON` points at the exact Nix interpreter and managed interpreter downloads are disabled. `uv.lock` remains the Python dependency/artifact lock; Nix supplies the common native tools. This preserves the simple `uv`/SDK development workflow.

This is reproducible tool and dependency selection, not a claim of a fully offline or bit-for-bit hermetic application/container build. First setup fetches the pinned Nix closure and locked Python artifacts. The observer image has an immutable multi-architecture base digest and pinned pytest/coverage versions; its pip installation is not a Nix-built application image. Docker daemon/VM configuration and provider responses are external state. Keep those boundaries explicit when interpreting an evaluation.

On macOS, the native shell does not install or start a Docker daemon. Start Docker Desktop or Colima's Linux VM. The Python Docker SDK reads `DOCKER_HOST`, not the CLI's selected context; if necessary expose the reviewed local context explicitly:

```bash
export DOCKER_HOST="$(docker context inspect --format '{{.Endpoints.docker.Host}}')"
docker info
just images
```

Only use a Docker context you trust: it controls where submitted source and containers run. Keep admitted sources under Docker Desktop/Colima's shared directories. A custom rootless Linux socket can similarly be selected with `DOCKER_HOST`. Do not relax runtime, mounts, network or cleanup policy to work around an unavailable daemon.

Source admission was explicitly Linux-only before this migration. This combined change enables macOS only when the same fd/no-follow capabilities are available, with no path-based fallback. Host/runtime qualification is recorded in [the platform guide](../platforms.md) and CI; tooling alone is not execution qualification. Nix itself is not a security sandbox for untrusted targets.

## Useful recipes

```bash
just -- verify evals/fixtures/case01/request.json evals/fixtures/case01/submission.json \
  --settings .state/settings.json --format human
just -- eval evals/datasets/dev.json --settings .state/settings.json --repeats 3
just -- eval-agent auditor evals/datasets/auditor-dev.json \
  --settings .state/settings.json --repeats 3
CORSAIR_TEST_TEMPORAL=1 just -- test-docker -q -W error
just -- test-temporal -q -W error
CORSAIR_LIVE_CONFIG=.state/settings.json just -- test-all -q -W error
```

Flags after a recipe are forwarded as literal arguments. Use the initial `--` to avoid ambiguity with Just's own flags, and run variadic recipes separately rather than appending another recipe name. Paths containing spaces, quotes, dollar signs or semicolons are not interpolated into shell source. The recipes never auto-load `.env`, manufacture credentials or retry a policy-blocked model request.

`just check` includes Ruff, Just formatting and warning-failing ty. `test-all` enables actual Docker and Temporal; the live-provider gate still needs its explicit configuration. Inspect passed/skipped counts and preserve failed cases rather than treating a skipped provider test as qualification.

## Updating tools intentionally

```bash
nix flake update nixpkgs
nix develop --command just sync check
nix develop --command just -- test -q -W error
```

Review the `flake.lock` diff, actual tool versions and affected native/CI results in a separate update PR. Do not let an ordinary development command rewrite the lock silently. CI uses `--no-update-lock-file`; Python recipes use `uv --locked`. Nix profile/direnv integration is optional and not required for the golden path.
