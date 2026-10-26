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

## Prerequisites and failure messages

`just check` starts with `just toolchain`, which runs `python3 scripts/check_toolchain.py`: a standard-library report of Just, uv, the `.venv` Python, the providers extra and the Docker client against what `nix develop` provides. A `FAIL` line exits non-zero; a `WARN` line names a divergence that otherwise surfaces later as one of the errors below. Run the script directly when `just` itself cannot parse the justfile. `just sync` first runs it with `--before-sync`, which refuses only a `.venv` that `uv sync` would keep although it cannot import the locked native wheels, and the test suite's `tests/conftest.py` stops with the same `FAIL` line before collection.

| Message or symptom | Cause | Remedy |
| --- | --- | --- |
| ``error: Unknown setting `default-list` `` from any `just` command | A Just older than the pinned 1.58.0 is first on `PATH` (outside the Nix shell). | `nix develop`, or `uv tool install rust-just==1.58.0`. `tests/unit/test_justfile.py` skips with this remedy rather than failing on the unpinned binary. |
| `FAIL  just` or `FAIL  uv` from `just toolchain` | The tool is missing or not the pinned version. | `nix develop`. |
| ``FAIL  .venv  Nix python expected libstdc++ on LD_LIBRARY_PATH`` from `just toolchain`, `just sync` or pytest (`Exit:` before collection) | A `.venv` created inside `nix develop` is used outside it. Nix's loader never searches the host's library directories, so the manylinux wheels with C++ extensions (protobuf, used by google-adk and temporalio, and frozenlist) cannot find `libstdc++.so.6` without the shell's `LD_LIBRARY_PATH`. uv keeps this `.venv` (it satisfies `.python-version`), so without the check the symptom is the `ImportError` below. | Re-enter `nix develop`, or recreate it outside with `uv venv --clear && uv sync --locked --all-extras`; that `.venv` then also works inside the shell. |
| ``WARN  python … recreates .venv for .python-version`` | `.venv` is not Python 3.12 (for example a 3.13 `.venv` from before the pin), so the next `uv run --locked` silently recreates it with default dependencies only. | `just sync`. |
| ``WARN  .venv  other python … recreates .venv`` | `UV_PYTHON` in your environment names another interpreter than `.venv`; the Nix shell no longer sets it. | Unset `UV_PYTHON`, or `just sync` to accept the recreation with all extras. |
| ``WARN  providers missing`` | `uv sync --locked` or a recreated `.venv` left out the optional `providers` extra (LiteLLM); only `just sync` passes `--all-extras`. | `just sync` (`uv sync --locked --all-extras`). |
| ``connector 'litellm' requires Corsair's providers extra`` from `corsair` or a test | Same as above, at model selection. ADK's chained message suggests `pip install google-adk[extensions]`; do not follow it, because LiteLLM is pinned in Corsair's `providers` extra in `uv.lock`. | `just sync`, or `uv sync --locked --extra providers`. |
| `ImportError: libstdc++.so.6: cannot open shared object file` while importing `google._upb._message` (protobuf) or `frozenlist` | Code ran on a Nix-built `.venv` outside the shell without going through the checks above (for example `.venv/bin/python` directly). | As for `FAIL  .venv  Nix python`. |
| ``warning: `build_system.requires = ["uv-build>=0.12.19,<0.13"]` does not contain the current uv version`` | The Nix uv is newer than the build-backend range; uv fetches the locked `uv_build` separately. | None needed; the build still uses the declared backend. |

## Local environment and file lifecycle

`just sync` creates/updates the canonical root `.venv/`; do not keep using a dated task environment. Private/generated roots, local credentials, databases and delivery archives are Git-ignored. Ongoing settings and Temporal persistence belong under `.state/`, immutable evidence under `.runs/`, and disposable or explicitly retained investigation material under `.work/`. See [local files and retention](local-files.md) before cleanup or moving state.

## One `.venv` in and out of the Nix shell

The interpreter is requested the same way on both sides: the committed `.python-version` (`3.12`). The Nix shell adds `UV_PYTHON_PREFERENCE=system` and `UV_PYTHON_DOWNLOADS=never`, so a new `.venv` inside it uses the shell's Python 3.12 (first on `PATH`, as in CI), and an existing 3.12 `.venv` is kept instead of being recreated without extras. Outside the shell uv picks a 3.12 it has or downloads, never 3.13.

The supported path is `nix develop` for everything, as CI does. If you must also work outside the shell on Linux, build `.venv` outside it (`uv venv --clear && uv sync --locked --all-extras`): that `.venv` passes the offline suite on both sides, because a non-Nix interpreter finds the host's C++ runtime outside the shell and the shell's `libstdc++` inside it. The reverse is not possible: a Nix-built `.venv` cannot import protobuf outside the shell, and the checks above fail on it. Inside the shell, a non-Nix `.venv` loads the shell's `libstdc++` through `LD_LIBRARY_PATH`, which with this `flake.lock` needs a host glibc of at least 2.38 (Ubuntu 24.04 has 2.39); on an older host keep to one side.

## What is pinned—and what is not

`flake.lock` pins the Nixpkgs input. The shell provides Python 3.12, uv, Just, Bash, the Docker client, and the Temporal CLI. `.python-version` selects Python 3.12 for uv in and out of the shell; `uv.lock` pins Python dependencies and artifacts. Python recipes use `uv --locked`, and CI enters the same shell with `--no-update-lock-file`.

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
