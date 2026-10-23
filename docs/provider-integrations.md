# Provider integrations

Implementations live at `adapters/<capability>/<provider>.py`. `scm/git.py`, `scm/github.py` and `scm/azure_devops.py` implement the same source-acquisition port; `sandbox/docker.py` and `sandbox/openshell.py` implement the same sandbox port. The CLI composes them explicitly. No application or agent selects a concrete implementation internally.

## Source acquisition

Use a case request's `source.provider` to select `git` (default), `github` or `azure_devops`. GitHub uses PyGithub's commit and archive APIs; Azure uses its official generated Git client and a commit-versioned ZIP request. Both providers are read-only. Source URLs must be canonical credential-free HTTPS URLs. SDK resources close on success and failure. See [source-control setup](provider-scm.md).

GitHub authentication uses `GITHUB_TOKEN`, then the existing `gh` authentication session for the correct host. Azure requires `AZURE_DEVOPS_PAT`. Credentials, signed download URLs and tokens are not cache metadata. GitHub archive redirects are bounded, require exact approved HTTPS origins, and use HTTPX's native cross-origin authorization stripping. Bounded ZIP/tar extraction rejects traversal, duplicate paths, escaping/cyclic links, reserved-metadata collisions, special files and size/count violations. Provider wrapper removal is explicit, not guessed from a single directory.

**Azure DevOps live validation is deferred at the user's request.** Native SDK signatures and scripted client/archive tests are covered, but no authenticated Azure acquisition is reported as a pass.

## OpenShell setup

Install the official OpenShell **v0.1.5 CLI** separately from the pinned Python SDK. Start or register a supported **local Docker-compute gateway**, and use the same Docker daemon through `DOCKER_HOST`. Runtime images must exist in that daemon. Rebuild the six checked-in images after this change: their `/work` directory is owned by uid/gid `1001:1001` for gateway admission, while Docker's original root-builder behavior remains unchanged.

```bash
make images
export CORSAIR_SANDBOX=openshell
# Use the registered gateway's native TLS/OIDC configuration, or set an explicit local endpoint:
export CORSAIR_OPENSHELL_GATEWAY_ENDPOINT=http://127.0.0.1:18084
export CORSAIR_OPENSHELL_CLI=openshell
# Copy and review this example, replacing its illustrative endpoint/executable before actual package downloads:
cp config/openshell-build-policy.example.yaml config/openshell-build-policy.local.yaml
export CORSAIR_OPENSHELL_BUILD_POLICY="$PWD/config/openshell-build-policy.local.yaml"
uv run corsair verify --case cases/path-traversal-fixture \
  --submission cases/path-traversal-fixture/reference-submission.json
```

The example policy is not enabled automatically. Any nonempty build script needs an explicitly reviewed build policy with endpoint and executable identities; an empty build remains offline. The adapter never automatically approves a registry or provider. Do not commit the local policy if it names private endpoints.

OpenShell sandbox lifecycle and ordinary build/probe execution use `SandboxClient`. The SDK does not install its CLI or expose high-level filesystem-transfer, snapshot or policy-set methods in this version.[1] Corsair therefore uses the official CLI for `policy set --wait`, and the existing local Docker control-plane primitives for trusted file transfer, original-source verification, collector execution and immutable snapshots. These operations target only the workload whose gateway ID, immutable container ID, exact labels, non-root user and isolation settings were verified. They never target the gateway or supervisor.[2] [3]

Build identity is `1001:1001`; probe identity is `1000:1000`. `/work` and kernel support files are frozen and owned by a different identity from the probe. The sealed image's OCI admission workdir is `/tmp`; actual SDK commands explicitly use `/work`. A writable temporary admission directory does not make source writable. Package homes are separate from the kernel support namespace. Hard Landlock requirements, no-new-privileges, dropped capabilities, CPU/memory/PID limits and offline probe policy are checked rather than assumed. Model credentials and inference clients stay outside workloads.

The adapter supports the Docker driver only, with no automatic Docker-execution fallback. Unknown drivers, unavailable services, insufficient isolation, missing credentials and ambiguous lifecycle operations fail explicitly. Commands and uncertain mutations are not automatically retried. Native names are mapped to the gateway's length limit without losing logical identity. Deletion verifies both the expected gateway ID and final name absence; same-name replacement is not confirmed cleanup.[4] Environment caches bind the runtime digest, source/build identities, provider and effective reviewed security policy.

## Validation

The final post-cleanup combined suite passed **278 tests in 143.30 seconds**: offline contracts, architecture boundaries, installed-wheel resources, existing real Docker regressions, and five opt-in real OpenShell gateway tests. `make check`, `uv lock --check`, distribution build and `git diff --check` passed. The [frozen provider receipt](provider-validation.json) records source digests, per-language twin identities and the explicit deferred/unsupported states.

Fresh live GitHub acquisition verified `X-McKay/playbooks` commit `2b31000fbc8c9a788448b049d25809927c4d91f9`, extracted 269 files including the cache marker, and reused the complete cache without constructing another SDK client.

A representative Docker vulnerable/fixed twin passed in each of Python, Java, JavaScript, TypeScript, Perl, Ruby and C++. This smoke is in addition to the historical 385-case Docker matrix recorded separately in [architecture validation](architecture-refactor.md); it is not a new claim that every full corpus case ran on OpenShell.

Actual OpenShell gateway testing verified non-root execution, root-policy refusal, offline policy replacement, full Python control/exploit and fixed-revision replay with native coverage, sealed-source write refusal, network denial and confirmed cleanup. JavaScript also passed a trusted twin. The complete post-cleanup test receipt records final counts and SDK/artifact identities. These tests use reviewed references and no model calls; they do not measure model accuracy.

**OpenShell is not yet validated for the entire seven-language framework matrix.** The first npm/Vite and Maven attempts were denied by the deliberately narrow registry policy; Ruby/Bundler control execution errored; GNU Make 4.3 recipe execution failed in Perl and C++ builds. The Make issue has an upstream report and a reported Make 4.4.1 workaround. No sandbox policy is weakened, failed case is reclassified as passed, or hidden fallback is used. See [exact compatibility constraints](openshell-compatibility.md).

Run offline tests with `make test-offline`. Run explicit real-gateway regressions with a configured local gateway and `CORSAIR_OPENSHELL_INTEGRATION=1 make test-openshell`; if opted in, unavailable prerequisites fail rather than silently skipping. A registered remote service and Kubernetes/Podman drivers are outside this validated scope.

## References

[1]: https://docs.nvidia.com/openshell/v0.1.5/sdk/python "OpenShell v0.1.5 Python SDK"
[2]: https://docs.nvidia.com/openshell/v0.1.5/how-it-works/sandboxes/overview "OpenShell sandbox lifecycle and policy controls"
[3]: https://github.com/NVIDIA/OpenShell/blob/v0.1.5/crates/openshell-driver-docker/src/lib.rs "OpenShell Docker compute-driver implementation"
[4]: https://github.com/NVIDIA/OpenShell/blob/v0.1.5/python/openshell/sandbox.py "OpenShell SDK identity and deletion semantics"
