# Linux amd64 and Apple Silicon macOS

Supported developer targets are **Linux amd64** (`x86_64-linux`) and **macOS arm64** (`aarch64-darwin`). The same locked Nix shell supplies native tools; the same Just recipes drive checks, packaging, evaluation and runtime commands. Intel Macs, Linux ARM and Windows are not the supported CI matrix.

Source admission checks the APIs it actually uses rather than accepting an OS name: `O_DIRECTORY`, `O_NOFOLLOW`, descriptor-relative open/stat, non-following stat and `scandir(fd)`. Missing capabilities reject admission. There is no pathname-walking fallback. The source replacement, symlink, archive and oracle-exclusion tests run on the real host filesystem.

These checks do not attest an arbitrary network, FUSE, synchronized-cloud or removable filesystem. Use a dedicated disposable workspace and test the filesystem that will hold source. Native targets still run only inside the reviewed Linux container, never inside the Nix shell on the host.

The Ruby recipe `ruby.secret_disclosure/1` runs in `corsair-ruby:0.1` (`deploy/ruby/Dockerfile`, Ruby 3.1 pinned by digest), selected through its `Settings.images` entry; `just images` builds it with the other reviewed images. The Ruby recipe is qualified on **Linux amd64 only**; its macOS arm64 and live-model gates are unrun. See the [Ruby corpus survey](corpus-ruby.md).

## Development and CI

```bash
nix develop
just sync check
just -- test -q -W error
just -- test-temporal -q -W error
```

The common `ci.yml` runs Linux amd64 jobs and a `macos-26` Apple Silicon job. Both enter the committed flake shell. macOS runs the complete offline suite—including actual descriptor admission, immutable artifacts and fresh installed-wheel checks—and real Temporal workflow/replay tests. Linux additionally runs the actual Docker/Temporal/ADK integration chain.

Hosted macOS ARM runners do not support nested virtualization. CI therefore does not pretend to run Docker Desktop/Colima there or silently substitute a mock daemon. Full Docker-chain qualification on a physical Apple Silicon Mac with its chosen VM is a separate operator gate. Tooling and host tests alone do not establish it.

## Runtime images per recipe kind

Each recipe kind selects its own reviewed image through `Settings.images` (see
[configuration](configuration.md)); `just images` builds every `deploy/*/Dockerfile`.
The Python secret-disclosure recipe uses `corsair-python:0.1`; the JavaScript
prototype-pollution recipe uses `corsair-javascript:0.1`. Both apply the identical
`DockerSandbox` isolation (read-only, offline, dropped capabilities, no-new-privileges,
CPU/memory/PID limits, immutable-identity cleanup). Image selection is a one-line mapping,
not a code path.

### JavaScript prototype pollution (Linux amd64)

The `javascript.prototype_pollution/1` recipe is qualified on **Linux amd64 only**, on one
real corpus row (`prototypepollution-a`). Its evidence:

- Image `corsair-javascript:0.1` from `deploy/javascript/Dockerfile`, pinned
  `node:22.23.3-bookworm-slim` by digest; the trusted driver
  `drivers/javascript/driver.mjs` runs `node --test` with the JUnit reporter and
  `NODE_V8_COVERAGE` line coverage, with no npm install and no network at run time.
- `corsair verify` on the frozen v3 row:
  `evals/datasets/chain/javascript/prototypepollution-a-v3/` — control held (exit 0,
  target line 2 covered), adversarial violated (exit 1, target line covered), cleanup
  confirmed, no security verdict rendered.
- `tests/integration/test_docker_javascript.py` (marker `docker`): control+violation,
  safe-variant hold, unexpected-exception error, absent-coverage invalid, and cleanup.
- Measured per-role container time ~0.16 s on the implementation host.

macOS arm64 and the full live chain for this recipe are **unrun**. A `node --test` run
produces machine-readable line coverage from V8 directly; no second test or coverage
engine is added.

## Docker on a physical Mac

Docker Desktop or Colima supplies the Linux VM/daemon. Nix provides the Docker client, not the daemon. If using Colima:

```bash
brew install colima
colima start
docker context use colima
export DOCKER_HOST="$(docker context inspect colima --format '{{.Endpoints.docker.Host}}')"
docker info
mkdir -p .work/tmp
export TMPDIR="$PWD/.work/tmp"
just images
just -- verify evals/fixtures/case01/request.json evals/fixtures/case01/submission.json \
  --settings .state/settings.json --format human
CORSAIR_TEST_TEMPORAL=1 just -- test-docker -q -W error --basetemp="$PWD/.work/pytest-tmp"
```

Docker Desktop's selected local context can be exposed similarly. The Python Docker SDK reads `DOCKER_HOST`, not the Docker CLI's context selection. Only use a trusted local Unix-socket context, and keep source/artifact staging under the VM's shared directories. A rootless Linux daemon can likewise be selected by its real `DOCKER_HOST` socket.

Python's default macOS temp tree can fall outside Colima's shared mounts. `TMPDIR` controls native observer staging, while pytest's `--basetemp` controls test fixtures. Both must remain under a reviewed shared directory. An unshared temp tree is an infrastructure failure, not a safe target result.

Do not use privileged targets, mount the Docker socket into target containers or relax the read-only, dropped-capability, no-new-privileges, offline-network, resource or cleanup policies to obtain a pass. Source admission remains on the host; container execution remains in the Linux VM.

The implementation sandbox is Linux ARM, outside the requested matrix. Its local full-suite results are regression evidence; target-platform qualification comes from the actual Linux amd64/macOS arm64 CI jobs. See [environment setup](../development/setup.md) and [current plans](../plans/README.md) for exact receipts and remaining limits.
