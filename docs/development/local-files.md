# Local files and retention

Private/generated files are excluded from Git and delivery packages. Ignoring a file prevents accidental publication; it is not access control, encryption or a backup. Keep public knowledge in `docs/`, frozen evaluation inputs and sanitized receipts in `evals/`, and generated delivery bundles in ignored `outputs/`.

## One development environment

Use the root `.venv/` created by the locked toolchain:

```bash
nix develop
just sync check
just -- test -q -W error
```

Do not point `UV_PROJECT_ENVIRONMENT` at a dated task directory for ongoing development. Recreate a virtual environment with uv rather than renaming it and running it elsewhere: console scripts and interpreter links can contain absolute paths. If an old root environment must be preserved for rollback, do not execute it at the backup path.

uv owns dependency/download/build caching. The normal uv cache is acceptable; if a repository-local cache is useful, set `UV_CACHE_DIR="$PWD/.cache/uv"`. Both caches are reproducible conveniences, not evidence or service persistence. Prefer uv's cache-management commands to a custom cache engine.

## Directory responsibilities

| Path | Contains | Retention |
| --- | --- | --- |
| `.venv/` | One validated installed development environment | Recreate from Nix/uv locks; not durable data. |
| `.cache/`, tool caches | Download/build cache and local tool output | Generated and private; exclude from Git/packages. |
| `.runs/` | Artifact blobs, immutable operation claims/commits and private reports | Keep complete stores for retained runs. Never prune arbitrary blobs or unknown-operation intents. |
| `.state/settings.json` | Reviewed ongoing operator configuration | Keep separate from source. Provider secrets remain in supported worker environment mechanisms. |
| `.state/temporal/` | Local Temporal persistence | Preserve consistent state and original run identity; no arbitrary live-database moves or resets. |
| `.state/temporal/history/` | Closed historical databases with provenance | Retained history, not an automatically restarted service. |
| `.state/backups/` | Verified rollback snapshots | Private, access-controlled; remove only after restore/retention decisions. A same-disk copy is not host-loss protection. |
| `.work/<task>/` | Temporary tests plus explicitly retained logs/checkpoints/failure investigations | Remove completed reproducible test copies after saving relevant evidence. Record why retained private artifacts are needed. |
| `.work/tmp/` | VM-shared disposable staging | Only clear once owning tests/containers have completed. |
| `outputs/` | Complete generated deliverables and sanitized reports | Share deliberately; do not commit built archives by default. |

Provider bridges, trust bundles and private keys have an owner and potentially active consumers. Their small size or old timestamp is not proof they can be deleted.

## Shared native staging on macOS

Keep Docker staging under a reviewed path shared with Colima/Docker Desktop:

```bash
mkdir -p .work/tmp
export TMPDIR="$PWD/.work/tmp"
export DOCKER_HOST="$(docker context inspect --format '{{.Endpoints.docker.Host}}')"
CORSAIR_TEST_TEMPORAL=1 just -- test-docker -q -W error \
  --basetemp="$PWD/.work/pytest-tmp"
```

Location changes do not relax container policy. Do not delete staging used by a running container or an investigation whose cleanup is uncertain.

## Local Temporal persistence

Start an explicitly owned local development service with its database under state, not task scratch:

```bash
mkdir -p .state/temporal
nix develop --command temporal server start-dev --ip 127.0.0.1 \
  --port 7233 --headless --db-filename "$PWD/.state/temporal/development.db"
```

Run this separately from the worker. It is not an unattended scheduler or production deployment. Do not start another service on an occupied port, reuse a historical database as a new qualification cohort, or kill unrelated processes. Worker and client settings must point at the intended service and artifact store.

For a database move, identify its owning process and stop/admit it deliberately. If ownership is uncertain, do not move it. Use a consistent SQLite backup, verify integrity and provenance, account for WAL/SHM/journal state, and only retire the old location after validation. Database files and histories may contain sensitive request/source/model material.

## Evidence retention and backups

Temporal history does not replace the artifact filesystem. Back up the entire configured artifact root—including `blobs/` and `operations/`—and required Temporal persistence separately. A missing intent or receipt cannot be interpreted as permission to repeat an uncertain side effect. See [disaster recovery](../operations/disaster-recovery.md).

Corsair intentionally has no broad `clean all`, artifact merger or automatic evidence garbage collector. The [current plan](../plans/README.md) records implemented cleanup, retained artifacts and unqualified recovery boundaries.
