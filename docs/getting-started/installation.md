# Install the development tooling

Corsair supports **Linux amd64** (`x86_64-linux`) and **Apple Silicon macOS** (`aarch64-darwin`) only. Windows, Linux ARM, and Intel macOS are outside the supported developer/CI matrix. Work on a dedicated, disposable host: source admission and target execution are not a reason to expose personal credentials, production data, or a Docker socket to a target container.

## Prerequisites

- A Git checkout of this repository. For a new working copy, clone the authorized repository URL and enter it:

  ```bash
  git clone <authorized-repository-url> corsair
  cd corsair
  ```

- [Nix with flakes enabled](https://nix.dev/install-nix.html). Enable both `nix-command` and `flakes`, or pass `--extra-experimental-features 'nix-command flakes'` to Nix commands.
- A **trusted, running Docker daemon** for native reference replay and investigations. The Nix shell supplies the Docker *client*, not a daemon. On macOS, Docker Desktop or Colima supplies a Linux VM/daemon; on Linux, the operator must already have a reviewed local daemon or socket. Do not point Corsair at an untrusted or remote daemon.
- A Temporal service only for durable investigations. The local development service is started in the first terminal of [the first-project guide](first-project.md), not by installation.

The committed flake provides Python 3.12, `uv`, Just, Bash, the Docker client, and the Temporal CLI. `flake.lock` pins that tool selection and `uv.lock` pins Python dependencies; first use can fetch those locked artifacts, and the setup is not a fully hermetic application or container build.

## Enter the locked shell

From the repository root:

```bash
nix develop
just sync
just
```

`just sync` installs the locked project dependencies and extras. The final command lists the available documented recipes; it does not start Docker, Temporal, a worker, or a model.

## macOS Docker VM and temporary files

Start and select a trusted Docker Desktop or Colima VM before using native execution. The Python Docker SDK reads `DOCKER_HOST`; selecting a Docker CLI context alone is insufficient. From the repository root, expose the selected local context and keep temporary staging on a directory that the VM shares:

```bash
export DOCKER_HOST="$(docker context inspect --format '{{.Endpoints.docker.Host}}')"
docker info
mkdir -p .work/tmp
export TMPDIR="$PWD/.work/tmp"
```

Colima may not share macOS's default `/private/var/folders` temporary tree. `TMPDIR` makes native observer staging use `.runs/tmp`; for pytest, use `--basetemp="$PWD/.work/pytest-tmp"` when its default temp path is not shared. These settings preserve the native observer boundary; they are not a fallback sandbox. Keep admitted source and artifact directories under reviewed VM-shared locations, and never relax container network, mounts, privileges, resource limits, or cleanup policy to work around a VM problem.

Continue with the [no-model reference replay](quickstart.md). For configuration fields, command semantics, and platform limits, use the [development setup](../development/setup.md), [platform reference](../reference/platforms.md), [configuration guide](../guides/configuration.md), and [CLI reference](../reference/cli.md). Current work and known limits are tracked in the [plans index](../plans/README.md).
