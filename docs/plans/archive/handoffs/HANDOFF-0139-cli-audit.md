---
id: HANDOFF-0139
kind: handoff
title: Implementation audit, SDK cleanup, and polished CLI
status: complete
updated: 2026-10-24
related: [PLAN-0106, HANDOFF-0138]
---

> Historical record. Commands, counts and status describe the recorded revision, not the current working tree. See [current work](../../README.md) for current guidance.

# Implementation audit, SDK cleanup, and polished CLI

## Delivered

The existing `manus/re-design` branch retains the playbook-aligned Plan 1 organization and now includes Rich terminal output/animation, clean JSON stdout, text or JSONL stderr logs, restricted JSONL mirroring, native activity lifecycle logs, read-only live SDK diagnostics, native investigation/batch watching, graceful SDK worker shutdown and explicit client detachment.

ADK event handling, callback contracts and tool factory signatures were simplified. CLI and activity share cancellation-safe native execution; scoring and human display share usage totals. Pydantic serializes nested batch receipts. Additional audit remediation covers descriptor-anchored source admission, cross-case evidence/result binding, the demonstrated pytest-failure observation forgery, and a bounded native final-record window with Temporal patch-marker compatibility.

Read the [implementation audit](../reviews/implementation-audit.md), [CLI reference](../../../reference/cli.md), [pilot runbook](../../../operations/runbooks/pilot.md), and [README](../../../../README.md) before changing scope.

## Qualification receipt

The final post-cleanup run completed successfully:

```bash
uv run --locked ruff check src tests evals/evaluators
uv run --locked ruff format --check src tests evals/evaluators
DOCKER_HOST=unix:///run/user/1000/docker.sock \
CORSAIR_TEST_DOCKER=1 CORSAIR_TEST_TEMPORAL=1 \
CORSAIR_LIVE_CONFIG=.state/live.json \
uv run --locked --extra providers pytest -q -W error
```

Result: **90 passed in 111.38 seconds**, no skipped tests in that run, warnings treated as errors. Ruff passed; 60 Python files were already formatted. `uv build` produced the source distribution and wheel. The suite itself installs the real wheel into a fresh virtual environment and exercises resources and the console outside the checkout.

Real-process CLI checks cover worker startup/SIGTERM shutdown, healthy and failed-dependency doctor reports, native reference execution, JSON stdout/log mirroring, Rich animation through a pseudo-terminal and client Ctrl+C detachment. The detachment test validates exit `130`, verifies the remote workflow remains running, then explicitly cancels it; its deliberately paused provider activity is labelled test-only. Native cancellation receipt waits allow the SDK heartbeat-throttled handshake, not an invented instant-cleanup guarantee.

Whole-chain/batch tests use a labelled scripted ADK model with genuine Docker and Temporal. Native history replay, cancellation, worker restart, source-race and cross-case regressions remain in the suite. The separate live provider test exercises the real outcome-blind auditor. These different boundaries must not be conflated with full live-producer accuracy.

The source archive and wheel are delivery artifacts, not committed private runtime state. `.state`, `.runs`, credentials, endpoints, native raw output, temporary diagnostic stacks and test-process scratch directories are excluded from the archive.

## Remaining limits

No runtime placeholder, mock provider selection, fabricated health response or host evidence fallback was found in the supported pilot paths. Test doubles remain deliberate, labelled and excluded from the wheel.

The live security producer request remains provider-policy blocked and unqualified. Do not silently switch providers or evade that block. General hostile-interpreter observer integrity remains outside this in-process Python pilot: the specific pytest-marker bypass is hardened, not universal attestation. A stronger independent observer boundary and an approved live provider require a design/qualification decision before broader production claims.

The pilot remains standard-library Python on Linux; source descriptor pinning is not atomic whole-tree snapshotting. Local artifact paths do not provide recovery after host loss. The ADK invocation-stop private bridge remains isolated because the pinned callback context lacks a public forwarding setter.

## Next actions

Use `make sync`, `make images`, and native `corsair verify` first. Then start the actual Temporal service and worker; run `corsair doctor` against the same settings. Freeze any new dataset before modifying prompts or policy. Preserve failed/unavailable rows and unknown accounting. Compare held-out human-labelled outcomes before expanding the recipe, observer or provider profile.
