# Security policy

Corsair is a personal-use security-investigation pilot, not an attestation boundary for arbitrary hostile target code. There are no declared production-supported release versions or remediation SLA. The security and recovery limits are part of the product: read [security architecture](docs/architecture/security.md), [agent safety](docs/agents/safety.md) and the [packaged risk assessment](src/corsair/policies/risk.md).

## Reporting a vulnerability

Do not post exploit payloads, credentials, private repositories, raw model traces, sensitive native receipts or target secrets in public issues. If private vulnerability reporting is enabled for `X-McKay/corsair`, use GitHub's private reporting route from the repository Security tab. Otherwise ask the repository maintainer for a private reporting channel without including sensitive reproduction details. This repository does not currently specify a separate security email address; do not assume or invent one.

A useful private report identifies the affected revision, entrypoint, trust boundary, prerequisites, observed impact, relevant native evidence and cleanup state. Distinguish application assertion failures from host, admission, dependency, sandbox-policy, provider and cleanup failures. Use sanitized summaries initially; agree on a safe transfer channel before sharing raw diagnostics.

## Safe operation

Run the pilot only on a disposable, reviewed host or VM. Do not run untrusted target code on the host. Keep workload credentials, the Docker socket and network access outside target containers. Models receive admitted source/context and narrowly scoped tools; oracle labels remain outside agent-visible input. Agents cannot weaken operator policies or authorize publication.

A failed benign control, missing report, unexpected exception, unknown execution, sandbox denial or unconfirmed cleanup is not evidence that an application is fixed or safe. Failed reproduction remains `INCONCLUSIVE`, never `REFUTED`. A scoped positive demonstration is not application-wide applicability or universal patch correctness.

Do not bypass TLS, change expected labels, relax source admission or automatically repeat uncertain native side effects to make a test green. Preserve immutable operation identities and retain attributable failures. Follow the [pilot runbook](docs/operations/runbooks/pilot.md) and [troubleshooting guide](docs/operations/troubleshooting.md).
