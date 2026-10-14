# Corsair v2 quickstart

This procedure creates an explicit local operator config and checks only its declared prerequisites. It does **not** claim that a model, Temporal worker, OpenShell gateway, or workload is qualified merely because setup completes.

## 1. Install the package and inspect the CLI

```shell
uv sync
uv run corsair-v2 --help
uv run corsair v2 schema operator --json > /tmp/corsair-v2-operator-schema.json
```

The distribution installs both `corsair` and `corsair-v2`. `corsair run` remains the historical CLI; all commands below explicitly select v2.

## 2. Choose real local values

Use a real digest-pinned image supplied by the operator. Do not type an invented digest into a config. For an image already present locally, Docker can print its repository digest:

```shell
export CORSAIR_IMAGE_REF='registry.example.org/security/python-runner:2026-10-14'
export CORSAIR_IMAGE="$(docker image inspect --format '{{index .RepoDigests 0}}' "$CORSAIR_IMAGE_REF")"
printf '%s\n' "$CORSAIR_IMAGE"
```

The final value must look like `registry.example.org/security/python-runner@sha256:` followed by 64 lowercase hexadecimal characters. If Docker prints `<no value>` or an unpinned tag, stop and obtain an image with a published repository digest. Corsair does not accept a Docker-only image ID or an unpinned tag.

Set paths to a real operator policy and an already-registered native OpenShell gateway name. The gateway is a registration name (not a URL); the native CLI/SDK uses its registered gateway and authentication context under the configured user's `HOME`. Bootstrap the registration using the [official OpenShell v0.1.3 documentation](https://github.com/NVIDIA/OpenShell/tree/v0.1.3/docs/kubernetes). Do not pass a raw mTLS gateway URL as Corsair's `gateway`, disable TLS, or create a Docker execution bypass.

```shell
export CORSAIR_HOME="$HOME/.local/share/corsair-v2"
export CORSAIR_CONFIG="$HOME/.config/corsair-v2/operator.json"
export CORSAIR_POLICY="$HOME/.config/corsair-v2/openshell-policy.yaml"
export CORSAIR_GATEWAY='corsair-local'

# The policy must already exist and must be operator-owned.
test -f "$CORSAIR_POLICY"
test -n "$CORSAIR_IMAGE"
```

`init` defaults to `qwen3:4b` with PydanticAI's native `ollama` provider, using its OpenAI-compatible local API at `http://127.0.0.1:11434/v1`. This provider-native Ollama profile is the default; a small model may still fail to use required tools or return the required typed output. Test the chosen model/profile against the task's real tool/schema contract and smoke dataset before meaningful use. A local server that requires no key needs no credential. For another OpenAI-compatible service, explicitly select `--provider openai-compatible` and set its credential only through the named environment variable—not in config:

```shell
export OPENAI_API_KEY='local-server-key-if-your-server-requires-one'
```

A local server that requires no key can leave this variable unset. The default base URL below is loopback-only. Do not use this example to contact a paid/cloud endpoint without consciously changing the config and its credential environment.

## 3. Create the actual config

```shell
umask 077
uv run corsair-v2 init \
  --output "$CORSAIR_CONFIG" \
  --storage-root "$CORSAIR_HOME" \
  --model qwen3:4b \
  --provider ollama \
  --base-url http://127.0.0.1:11434/v1 \
  --image "$CORSAIR_IMAGE" \
  --policy "$CORSAIR_POLICY" \
  --gateway "$CORSAIR_GATEWAY"

stat -c '%a %n' "$CORSAIR_CONFIG"
python -m json.tool "$CORSAIR_CONFIG"
```

`init` emits a complete `operator-v2` JSON config and uses exclusive creation, so rerunning it at the same path correctly fails instead of replacing policy/model/storage choices. `init` does not offer `--cli-path`; if an alternate OpenShell CLI binary is required, inspect the emitted config and set the actual `sandbox.cli_path` field in a manually controlled config. Inspect the config with standard tooling if needed; it contains no API-key value.

## 4. Run a bounded doctor check

```shell
uv run corsair-v2 doctor --config "$CORSAIR_CONFIG"
```

The command reports locked dependency versions, the actual OpenShell CLI/SDK/profile/gateway observation, qualification state, and a native Temporal connection check. It makes no inference call. A missing CLI, unavailable gateway, or unavailable Temporal server is returned as `ok:false` and a nonzero process status, not as a fake healthy profile.

To opt into an unauthenticated, read-only local model check, use:

```shell
uv run corsair-v2 doctor --config "$CORSAIR_CONFIG" --inference-health
```

This performs `GET /models` only against configured loopback HTTP(S) endpoints. For a non-loopback endpoint, the operator must repeat it explicitly with `--approved-base-url https://approved.example/v1`; this is still a health read, not an inference request. No provider health check is automatic.

## 5. Validate a run spec before running it

A run spec is a JSON document conforming to the live schema—not an arbitrary shell recipe. Inspect the schema first:

```shell
uv run corsair-v2 schema run --json > /tmp/corsair-v2-run-schema.json
```

Create `run.json` only for an already acquired local repository at an exact commit. For example, replace the environment values with a real absolute checkout and actual 40-hex commit:

```shell
export TARGET_REPOSITORY="$HOME/src/your-already-acquired-repository"
export TARGET_COMMIT="$(git -C "$TARGET_REPOSITORY" rev-parse HEAD)"
test "${#TARGET_COMMIT}" -eq 40

cat > run.json <<EOF
{
  "schema_version": "run-v2",
  "request_id": "local-example-001",
  "source": {
    "path": "$TARGET_REPOSITORY",
    "commit": "$TARGET_COMMIT"
  },
  "concern": "Assess the explicitly scoped reported security condition in the captured revision.",
  "language": "python",
  "framework": "pytest",
  "cwe": ["CWE-22"]
}
EOF
```

The engine captures source through the trusted source service; it never fetches an arbitrary URL or executes host source. If the prerequisite runtime is absent or unqualified, the result remains an honest refusal/failure rather than falling back to host execution.

## 6. Run direct or durable, then inspect private artifacts

A direct run calls `engine.run`:

```shell
uv run corsair-v2 run \
  --config "$CORSAIR_CONFIG" \
  --spec run.json \
  --output-dir "$CORSAIR_HOME/operator-reports/local-example-001"
```

A durable run submits to native Temporal and waits for its `RunResult`:

```shell
uv run corsair-v2 run \
  --durable \
  --config "$CORSAIR_CONFIG" \
  --spec run.json \
  --output-dir "$CORSAIR_HOME/operator-reports/local-example-001-durable"
```

Start `worker --config "$CORSAIR_CONFIG"` in a separately supervised terminal before submitting durable work. Use `submit`, `status`, `cancel --graceful`, `history export`, and `history replay` when operating the durable lifecycle. History exports are private because Temporal payloads can contain sensitive workflow data.

Each successful engine result export contains private `result.json`, `evidence.json`, and `report.md`. A report records only bounded native observations; it does not turn a model plan, a passing assertion, an absent failure, or unqualified sandbox execution into a broad security guarantee. `unsupported`, cancellation, and platform failures exit nonzero even when a retained result report exists.

## 7. Exercise datasets and evaluate intentionally

Write the bundled native smoke Dataset, then evaluate only after the selected model/runtime is intentionally available:

```shell
uv run corsair-v2 benchmark smoke --output "$CORSAIR_HOME/corsair-smoke-v1.yaml"
uv run corsair-v2 eval \
  --config "$CORSAIR_CONFIG" \
  --dataset "$CORSAIR_HOME/corsair-smoke-v1.yaml" \
  --mode source \
  --repeat 1 \
  --max-concurrency 1 \
  --output-dir "$CORSAIR_HOME/evals/smoke-local"
```

Smoke output is an internal wiring measurement: it is source-only, generated development data, and cannot be promoted as a production baseline. For OWASP, PrimeVul, or Vul4J use the explicit import commands in [the operator guide](README.md); require checksums, immutable local inputs, licenses/provenance, selected IDs, and local repository mappings as applicable. The importer never downloads or runs dataset-provided commands.

Evaluation exports keep all attempts, blocked/abstaining cases, and task errors. `null` token/tool/request values mean unavailable telemetry, not zero use. Compare only compatible immutable reports, and promote only non-smoke reports with retained dataset identity.

## Current limits

- A package installation or successful `doctor` connection does not qualify OpenShell, Temporal workflow execution/replay, a provider, or semantic model accuracy.
- `Sandbox.qualified()` requires the exact certificate bindings documented in [OpenShell boundary](openshell.md), including observed effective policy and runtime identities; the development profile is ordinarily unqualified.
- Source-only `analyze` and source evaluations are not execution evidence. Full run evaluations remain subject to source capture, independent probe validity, sandbox, report, and evidence gates.
- Corsair never automatically sends telemetry or a cloud inference request. Operator action and explicit configuration remain the authorization boundary.
