---
id: PLAN-0106
kind: plan
title: CLI audit, diagnostics, and operator output
status: implemented
updated: 2026-10-24
related: [PLAN-0105]
---

# CLI audit, diagnostics, and operator output

## Purpose

Define and validate a polished operator interface for the durable ADK + Temporal pilot without adding a second orchestration layer, speculative health data, or unsafe observability. This plan covers CLI rendering, operational diagnostics, workflow inspection, log confidentiality, and SDK-native shutdown/connect behavior.

**Status: implemented and verified for the declared pilot scope.** The post-cleanup suite passed 90 tests with warnings treated as errors and actual Docker/Temporal/CLI gates enabled. Exact receipts and remaining live-producer/attestation limits are in [HANDOFF-0139](../handoffs/HANDOFF-0139-cli-audit.md).

## Required contract

### Output and global controls

- Support `--format auto|human|json`, `--no-color`, `--no-animation`, `--log-format text|json`, `--log-level DEBUG|INFO|WARNING|ERROR`, and `--log-file PATH` before or after a command.
- In `auto`, use a compact Rich human interface on an interactive terminal and JSON when stdout is piped. Explicit `human` and `json` override detection.
- Keep `--format json` stdout as JSON only. Put operational diagnostics/logs on stderr; mirror the same sanitized events to `--log-file` when configured.
- Keep existing explicit `--output` report paths for `eval` and `rescore`.
- Show a completed human result panel containing reason, scope, control, adversarial, audit, usage, and artifact identity. Do not claim an unobserved phase or invent progress.

### Logging confidentiality

- JSON logs must use a whitelist of safe operational metadata, rather than serializing arbitrary objects or exceptions; raw SDK diagnostics that may carry request data must be suppressed.
- Never log prompts, source content, payloads, secrets, provider responses, or raw model reasoning.
- Redact configured endpoint URLs and values of known credential environment variables from exception text before it reaches text or JSON logs. With `--log-format json`, expected CLI errors must remain JSON Lines diagnostics rather than become a plaintext second channel.
- Document that logs remain restricted operational diagnostics because IDs, timestamps, and local context can still be sensitive.

### Operational preflight and inspection

- Add `corsair doctor` that checks actual Docker daemon reachability, configured image, Docker runtime, settings/configuration, source/artifact directories, configured Temporal namespace, and task-queue worker pollers.
- Do not make model calls or provider credential checks in `doctor`, and do not describe it as model or security qualification.
- Keep doctor read-only. It must not build images, create directories, start workers, mutate source, submit work, or change Docker/Temporal state.
- Make `inspect ID --online` use native Temporal workflow status queries. Investigation status reports the actual phase and round; evaluation status reports actual completed and total child work.
- Make `inspect ID --online --watch` continue status observation and then wait for the actual workflow result. It must not fabricate a percentage or infer model progress from client-side timing.

### SDK lifecycle behavior

- Connect through the configured Temporal SDK client/namespace without adding a custom application retry policy around connection or operation calls.
- On worker `SIGTERM`, use the Temporal SDK `Worker` context and a `graceful_shutdown_timeout` of 45 seconds for orderly shutdown.
- On client Ctrl-C during `--wait`/`--watch`, detach locally and return exit `130`; do not automatically cancel the remote workflow. Cancellation remains the explicit `corsair cancel ID` action.
- Keep the final result-recording activity distinct from the request action budget: its 90-second schedule-to-close window includes scheduling, retry, and backoff. This retryable final recording does not certify an unrecorded native operation or solve host-loss recovery.

## Documentation obligations

The README must lead with an actual Docker-backed native reference replay before the model/Temporal workflow path. It must provide copyable interactive and pipe-safe JSON examples, the four exit outcomes (`0`, `1`, `2`, `130`), recovery behavior, and links to the detailed [CLI reference](../../cli.md) and [pilot runbook](../../runbooks/pilot.md).

The CLI reference and runbook must state the exact limits: the original live security-producer request was provider-policy blocked; a block does not establish full live-chain accuracy; scripted ADK models are confined to labelled tests and are never a production fallback. They must not invent test counts, provider qualification, model credential verification, Docker/Temporal health, or security conclusions.

## Validation gate before implementation status changes

The implementation owner must run and record the actual commands/results appropriate to the completed code, including at minimum:

1. parser coverage showing every global switch accepted before and after each applicable command, JSON stdout purity, human/no-colour/no-animation behavior, log mirroring, allowlisted/redacted logs, and exit handling;
2. Docker-backed doctor success and failed dependency paths for daemon, image, runtime, source/artifact configuration, Temporal connection/namespace, and missing task-queue poller—using real SDK calls rather than mocked health claims where the environment permits;
3. actual Temporal investigation/evaluation status-query and `--watch` behavior, including actual final result retrieval and no fabricated progress;
4. worker SIGTERM behavior using the SDK worker context and 45-second graceful shutdown configuration, plus Ctrl-C client detachment without workflow cancellation;
5. final-recording schedule-to-close/retry behavior, with the 90-second queue/retry/backoff-inclusive bound distinct from the investigation action budget; and
6. `make check`, applicable real Docker/Temporal tests, and an installed-wheel CLI smoke outside the checkout; and
7. documentation review against `README.md`, `docs/cli.md`, and `docs/runbooks/pilot.md` for correct limitations and no invented counts.

A passing scripted test exercises only its declared fixture/integration boundary. It cannot stand in for a blocked live producer or a full live-chain accuracy claim.
