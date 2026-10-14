# OpenShell cluster for the v2 backend

This runbook builds a fresh single-node kind cluster with Calico, Agent Sandbox and the official OpenShell 0.1.3 gateway on RIG0. It then loads the v2 runtime-matrix images into the node and writes the operator config that the v2 OpenShell sandbox backend reads (`CORSAIR_WORKSPACE=openshell`). Every pin comes from [deploy/runtime-lock.yaml](../../deploy/runtime-lock.yaml). The chart profile is [deploy/openshell/values.yaml](../../deploy/openshell/values.yaml): mTLS caller authentication, TLS on, no anonymous users, discovery preflight on. The architecture is [SPEC-0082](../development/specs/SPEC-0082-corsair-v2-architecture.md).

Status: the targets come from the last develop commit before the v1 removal (9c3bc62), where they qualified on RIG0. The v1 runbooks behind them (local platform, admission, gateway, toolchains) and their SPEC/PLAN records are still on `main`, not on develop. `openshell-images-load`, `openshell-config` and `qualify-openshell-v2` are new and have not run live. A green offline suite says nothing about a live cluster.

## Before you start

- **Host.** Linux amd64, a local Docker daemon at `/var/run/docker.sock`, `uv`, and Python 3.12. The remote Docker context variables are cleared on purpose.
- **One cluster on RIG0.** The cluster is always named `corsair`, so RIG0 runs one at a time. The worktree that created it owns it through `.state/kind/owner.json`. No other checkout adopts or deletes it.
- **Use your own worktree.** Work in `/home/al/git/corsair/.worktrees/<branch>`, and keep its evidence under that worktree's own `.runs/`. `openshell-install` accepts admission evidence only from the running checkout's `.runs`, with the same runtime lock and the same node UID. Evidence copied from another checkout is refused.
- **Creating the worktree.** `git worktree add` needs Al to run it, or an allow rule such as `Bash(git worktree add:*)` in the session's settings. `deploy/rig0/settings.local.json`, which held the old v1 allow list, is still on `main` and was not restored.

## Fresh-cluster sequence

`RUN` names one directory for this attempt's qualification evidence, for example `.runs/openshell-v2-20261014`. Each `CORSAIR_QUAL_RUN` path must not exist yet.

```shell
cd /home/al/git/corsair
git fetch origin
git worktree add .worktrees/<branch> origin/<branch>        # Al, or the allow rule above
cd .worktrees/<branch>

make tools                                                  # checksum-verified kind + kubectl in .tools/linux-amd64
make -C /home/al/git/corsair/.worktrees/<previous> openshell-forward-stop   # only if that checkout has this target and a forward
make -C /home/al/git/corsair/.worktrees/<previous> kind-down                # in the worktree that owns the current cluster
make kind-up                                                # kind 0.33.0, Kubernetes 1.35.8, Calico 3.33.0

make admission-artifacts                                    # helm + OpenShell CLI + chart + Agent Sandbox/storage, all hash-checked
make admission-install                                      # local-path storage + Agent Sandbox controller
make qualify-admission CORSAIR_QUAL_RUN=$RUN/admission      # storage remount + native kernel capability probe
make openshell-install CORSAIR_ADMISSION_RUN=$RUN/admission # official chart into namespace openshell
make qualify-network CORSAIR_QUAL_RUN=$RUN/network          # Calico ingress/egress controls on ordinary pods

make toolchain-images [TOOLCHAINS="python java"]            # build the images and run their trusted controls (Docker only)
make openshell-images-load                                  # load matrix images into the node -> .state/openshell/images.json
make openshell-config                                       # client mTLS, loopback forward, CLI check -> .state/openshell/config.json
make qualify-openshell-v2 CORSAIR_QUAL_RUN=$RUN/openshell-v2
```

- **Previous holder.** `kind-down` must run in the worktree that created the current cluster. It refuses when there is no ownership receipt or when the node container was replaced.
- **Network qualification.** `qualify-network` creates and deletes its own namespaces. It can run any time after `kind-up`. It checks the CNI, not OpenShell.
- **Gateway controls.** `make qualify-gateway CORSAIR_QUAL_RUN=$RUN/gateway` is optional. It checks TLS, caller authentication, generated identity and workload access isolation against the installed gateway. It then **uninstalls the gateway and deletes `.state/openshell`**. Run `openshell-install` again with the same admission evidence before `openshell-images-load`.
- **Image tags.** `toolchain-images` refuses to run when an earlier attempt is still in `.cache/toolchains/<dir>`. Inspect or archive that directory first; never delete it to force a rebuild. A build tags the image `corsair-<dir>:<source hash>`. `openshell-images-load` loads only the `image` tags listed in [deploy/v2/runtime-matrix.yaml](../../deploy/v2/runtime-matrix.yaml), and only those already in local Docker. Docker is shared across worktrees, so images built earlier still count. A tag that is not in local Docker is printed and left out of `images.json`. A rebuild from changed sources produces a new tag, and that tag only counts after the matrix row is updated.
- **Config refresh.** `openshell-config` can be rerun at any time. It stops the forward it recorded earlier, exports the client identity again, starts a new forward and rewrites the config. Set `OPENSHELL_PORT=<port>` to pin the local port; by default it picks a free one.
- **Backend tests.** `qualify-openshell-v2` runs `pytest tests/v2 -m openshell` with `CORSAIR_WORKSPACE=openshell`, `CORSAIR_OPENSHELL_CONFIG=<worktree>/.state/openshell/config.json`, `CORSAIR_EVIDENCE_DIR=<absolute $CORSAIR_QUAL_RUN>` and `--evidence-dir`. It runs the live half of `tests/v2/test_sandboxes_port.py` (the port suite Docker also runs) and of `tests/v2/test_workspace_openshell.py` (PydanticAI's `WorkspaceBackendSuite` against `OpenShellWorkspace`). The port suite uses the first tag in `images.json` unless `CORSAIR_OPENSHELL_IMAGE` names another.

## One case on OpenShell and on Docker

After `qualify-openshell-v2` passes, run the same case once per backend, one model user at a time (the live-inference rule), and compare the verdict, terminal reason, per-probe outcomes and cleanup in the two run records:

```shell
CORSAIR_WORKSPACE=openshell CORSAIR_OPENSHELL_CONFIG=$PWD/.state/openshell/config.json \
  uv run --locked corsair-v2 run --case <case> --provider-config <provider.json> --run-root $RUN/e2e-openshell
uv run --locked corsair-v2 run --case <case> --provider-config <provider.json> --run-root $RUN/e2e-docker
```

On OpenShell an Environment is not an image: replay seals a manifest under `state_dir`, and each probe's fresh sandbox replays that recipe on the runtime image before the probe file is written. Only the runtime-matrix images need loading. A `cmdi` case already decisive on Docker is the natural first choice.

**Known differences from Docker.** These are expected, not defects to fix by weakening anything:

- Environments replay per probe. Docker commits the replayed sandbox to an image; OpenShell cannot snapshot, so each probe's sandbox reruns the recipe's setup and then its baseline test (offline, under `none`) before the probe file is written. The sealed manifest pins the base image's digest ref, the recipe digest and the tree digest, and opening refuses if any of them changed. A non-hermetic setup (an unpinned dependency, a registry change) can therefore produce a different environment than the one Build validated; that shows up as a failed baseline or an infra failure for that probe, never as a silent pass. Each open's replay log is kept at `state_dir/environments/opens/<sandbox>.log`, and a failure names its sha256.
- Trusted code works in `/sandbox` (OpenShell's native workdir) instead of Docker's `/work`: the toolchain images run as uid 10001 and have no `/work`. The filesystem policy allows writes only to that workdir (`include_workdir`), `/tmp` and `/dev/null`. A recipe that writes to `$HOME` (unless `HOME` is under `/tmp` or `/sandbox`, as in the toolchain images that set `HOME=/tmp`) or into system site-packages fails on OpenShell where it passes on Docker. That stays so until the live policy gate decides otherwise (for example by putting `HOME` under `/sandbox`).
- Sandbox names are at most 19 characters (the 0.1.3 gateway's limit), so most are `cv2-<15 hex>`; the full port name is in the `corsair.v2.name` label.
- On OpenShell, `diagnose` and `execute` activities get the replay's setup and baseline bounds on top of Docker's start-to-close timeout, because each opens its environment by replaying it (`workflow.container_timeout`).
- `image_id` (the run record's `image_digest`) on OpenShell is the runtime image's digest ref (`docker.io/library/<repo>@sha256:...`) the probe sandbox was created from, not an environment image: there is none.

## Backend config

`.state/openshell/config.json` (mode 0600). Every path in it is absolute.

```json
{
  "endpoint": "127.0.0.1:<port>",
  "ca": "<worktree>/.state/openshell/cli/openshell/gateways/corsair/mtls/ca.crt",
  "cert": "<worktree>/.state/openshell/cli/openshell/gateways/corsair/mtls/tls.crt",
  "key": "<worktree>/.state/openshell/cli/openshell/gateways/corsair/mtls/tls.key",
  "workspace": "default",
  "gateway": "corsair",
  "cli": {"path": "<worktree>/.tools/linux-amd64/openshell", "sha256": "<runtime-lock openshell.cli.binary_sha256>"},
  "cli_env": {"XDG_CONFIG_HOME": "<worktree>/.state/openshell/cli"},
  "images": "<worktree>/.state/openshell/images.json",
  "policies": {"none": "<worktree>/policies/openshell/v2/none.yaml", "build": "<worktree>/policies/openshell/v2/build.yaml"},
  "state_dir": "<worktree>/.state/openshell/environments",
  "limits": {"ready_seconds": 300, "delete_seconds": 120}
}
```

| Field | Meaning |
| --- | --- |
| `endpoint` | Gateway address as `host:port`, the form the Python SDK `SandboxClient` takes; the CLI was registered with `https://<endpoint>` |
| `ca`, `cert`, `key` | Client mTLS files exported from the chart's `openshell-client-tls` Secret; mode 0600 |
| `workspace` | OpenShell workspace used for every sandbox |
| `gateway` | Gateway name the CLI uses with `--gateway` |
| `cli.path`, `cli.sha256` | The pinned OpenShell CLI and the binary hash the backend must verify before each use |
| `cli_env` | Environment the CLI needs on top of PATH and the locale variables; `XDG_CONFIG_HOME` is where `gateway add` stored the gateway and where the mTLS files sit |
| `images` | Path to `images.json` |
| `policies` | Operator policy files for the backend's `none` (no network) and `build` (registry egress) sandboxes; the backend owns these files and the config only points at them; `.runs/openshell-config/<id>/scope.json` records whether each one existed |
| `state_dir` | Private directory for the backend's per-environment state; created with mode 0700 |
| `limits` | Operator budgets in seconds, for sandbox Ready and for confirmed deletion |

`.state/openshell/images.json` maps each local tag, written exactly as in the runtime matrix, to the digest reference in the node:

```json
{"corsair-java:c7e6b24f0068035d": "docker.io/library/corsair-java@sha256:<manifest digest>"}
```

For each tag, `openshell-images-load` does the following:

1. Runs `kind load docker-image <tag> --name corsair`.
2. Reads the image's digest from `ctr -n k8s.io images list` on the node.
3. Fetches that content with `ctr content get` and checks that its SHA-256 equals the digest.
4. Checks that the manifest's config digest, or the digest itself, equals the local Docker image ID.
5. Tags the image `docker.io/library/<repo>@sha256:<digest>` in the node.
6. Checks that the reference resolves to the same digest.

## Evidence and private state

Evidence goes to the worktree's own `.runs/`:

| Step | Evidence |
| --- | --- |
| `tools`, `kind-up`, `kind-down` | `.runs/bootstrap/<id>/`: command receipts, runtime-lock copy, `cleanup.json` on `kind-down` |
| `admission-artifacts` | `.runs/artifacts/<id>/`: Helm pull/render receipts, with Secret values redacted |
| `admission-install` | `.runs/admission-install/<id>/` |
| `qualify-admission`, `qualify-network`, `qualify-gateway` | `$CORSAIR_QUAL_RUN/`: `junit.xml`, `scope.json`, `runtime-lock.yaml`, command receipts; admission also writes `admission/admission.json` and `admission/cleanup.json`, which `openshell-install` reads |
| `openshell-install` | `.runs/gateway-install/<id>/`: `owner.json` (namespace and node UIDs), `result.json` |
| `toolchain-images` | `.runs/toolchains-image/<id>/`; build receipts in `.cache/toolchains/<dir>/build.json` |
| `openshell-images-load` | `.runs/openshell-images/<id>/`: `images.json`, `load.json` (node UID, digests, tags missing locally) |
| `openshell-config` | `.runs/openshell-config/<id>/`: `config.json` (paths only), `native-status.json`, `port-forward.json`, `scope.json`, credential-withheld export receipts |
| `qualify-openshell-v2` | `$CORSAIR_QUAL_RUN/`: `junit.xml` (pytest) and `cleanup.jsonl` (one line per sandbox the live tests removed: backend, name, whether its absence was confirmed; a test fails on any unconfirmed line) |

Private state lives in `.state/`. It is ignored by Git and is never evidence:

- `.state/kind/`: the kubeconfig and the cluster ownership receipt.
- `.state/openshell/`: gateway `owner.json`, `images.json`, `config.json`, `port-forward.json` and `port-forward.log`, the CLI home with the client mTLS files, and `environments/`.

Do not copy `.state/`, Secrets or kubeconfigs into `.runs/`, Git or messages.

## Teardown

```shell
make openshell-forward-stop    # signals the recorded forward only if its pid still runs the recorded argv
make kind-down                 # refuses while a forward is recorded; deletes the cluster, then .state/openshell
```

`kind-down` confirms that the node container is absent before it removes `.state/kind` and `.state/openshell`. The gateway and its client identity existed only inside that node. Evidence under `.runs/` is kept. If any cleanup step fails, keep the state as it is and inspect it before trying again.

## Where failures belong

Each failure belongs to one layer. Keep that layer's receipts with the failure.

| Layer | Steps |
| --- | --- |
| Host or admission | `kind-up`, `qualify-admission` |
| CNI | `qualify-network` |
| Chart or gateway | `openshell-install`, the gateway readiness check in `openshell-config` |
| Transport | port-forward readiness, CLI `status` connection and authentication |
| Image | `toolchain-images`, `openshell-images-load` |
| Backend | `qualify-openshell-v2` |

Never disable TLS, permit anonymous users, skip preflight or the content-hash check, or edit the runtime lock to get a step through.
