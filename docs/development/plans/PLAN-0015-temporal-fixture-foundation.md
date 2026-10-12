---
id: PLAN-0015
kind: plan
title: Native Temporal fixture foundation
status: complete
updated: 2026-10-11
related: [SPEC-0013]
---

# Native Temporal fixture foundation

## Objective and dependencies

Implement [SPEC-0013](../specs/SPEC-0013-temporal-fixture-foundation.md), one Milestone 3 native fixture composition. OpenShell ISSUE-0006 and real providers do not block this independent fixture component. Root owns shared dependency/configuration and CLI acquisition; this agent owns `src/corsair/workflows`, `tests/temporal` and these records. No shared cluster/state/install mutation or publication by the agent.

## Steps

- [x] Inspect source/branch/handoff and reserve unused record IDs; research current primary immutable releases and native API guidance.
- [x] Implement small vendor-free payloads, one native parent/child, separate preparation/completion activities and explicit retry/cancellation semantics.
- [x] Add meaningful offline and explicitly selected native service tests with history export/replay.
- [x] Validate installed SDK APIs and offline component checks after root installs shared dependencies.
- [x] Run actual local persistent service checks under root-assigned process/port/state ownership; retain failed attempts.
- [x] Review, update qualification limits/results and deliver owned-file handoff to root for shared CURRENT/handoff/publication.

## Validation and progress

Private evidence root: `.runs/parallel-foundations-20261011/temporal-agent`. Primary release/docs were retrieved via web and Context7; sandboxed host urllib metadata retrieval failed DNS (`Temporary failure in name resolution`) for five official endpoints. That failed research path started no services and changed no dependencies. Root is handling authorized network acquisition.

Installed native temporalio 1.34.0 APIs passed initial direct `.venv/bin/python` ActivityEnvironment/schema checks (6 passed / 0.11 seconds; six native service cases skipped without an endpoint). Native default conversion coverage increased offline checks to seven / 0.10 seconds. Review added preconnection evidence-collision refusal: final offline component checks passed eight / 0.11 seconds. Skipped native cases never established readiness.

Root assigned verified CLI 1.9.1 and exclusive loopback 17333/17334/17336 with private SQLite state. The first sandbox service attempt failed before creation at `socket()` EPERM; authorized execution of the same owned operation proceeded through escalation. Actual native attempt 001 passed 13 / 3.40 seconds, then post-restart probe assertion failed because an untyped reconnected native handle returned a dict. Fixed with native `get_workflow_handle_for`, preserving failure/native state. Fresh attempt 002 passed 13 / 3.41 seconds and restart/replay; attempt 003 passed 13 / 3.41 seconds with stronger child history-prefix admission. Root/independent review then found evidence reuse before dispatch and missing parent-run binding. Fixed both using preconnection fresh-directory admission, exclusive writes and native pinned parent/child run histories; no custom job state/retry engine added.

**Final reviewed attempt 004 passed:** `PYTHONPATH="$PWD/src:$PWD" .venv/bin/python -m pytest tests/temporal --temporal-address 127.0.0.1:17333 --temporal-evidence-dir <native-004>/histories --junitxml <native-004>/native-junit.xml -q` passed 14 / 3.41 seconds. Separate `python -m tests.temporal.checkpoint prepare` and `resume` processes passed 0.314/0.414 seconds across original owned native service stop/restart with the same SQLite file. Fourteen actual final histories replayed (12 Completed, two Cancelled). Frozen 13 source/test/shared-lock/runtime-pin/Makefile inputs match after execution; source-freeze SHA256 `36d1d59074a4146ba005cef942780cfd4ce4880fc5d5190816dd74d64dc0a1c1`. Both original service process identities reaped exit 0, original `/proc` identities absent and all three endpoints closed. Raw commands, histories, JUnit, frozen bytes, failed earlier attempts and ownership receipts remain private under this evidence root.

[Qualification report](../../qualification/temporal-fixture-foundation.md) and [runbook](../../runbooks/temporal-fixture.md) retain exact scope. Review used native dependency/authority/evidence/cancellation/retry checks and an independent sibling agent audit for root. Tracing, cross-version replay, process crash/mid-activity interruption, resource cleanup, production databases/auth/TLS, artifacts/OpenShell/providers and full Milestone 3 remain **unrun/unqualified**. Source compilation and whitespace checks passed. Root owns repository-wide `make test-config`, CURRENT/handoff and publication; this completed scoped plan does not claim their future result.

Final record guards passed four / 0.03 seconds. Root reported integrated `UV_OFFLINE=true make test-config` passed 182 / 5.03 seconds with one attributable PydanticAI `run_sync` deprecation warning. Root and independent sibling raw audits confirmed native-004 frozen/current bytes, real parent/child/retry/cancellation histories, original persistent prefixes and exact process cleanup; sibling audit remains private at `openshell-agent/temporal-native004-audit.json`. Publication and shared CURRENT/handoff stay root-owned and are not claimed complete by this component record.

Final staged review found an extra blank line at EOF in `tests/temporal/support.py`, which unstaged diff checks did not inspect when the file was initially untracked. Removed that trailing blank line only. It is the sole current input-byte difference from native-004; its preserved frozen bytes remain the exact qualification source, the other 12 inputs match, and there is no behavior change or new live run. Root reruns final offline/whitespace guards after this formatting fix.

## Decisions and next action

Selected metadata-compatible tuple: Python 3.12, temporalio 1.34.0, PydanticAI/Evals 2.55.0; local development CLI 1.9.1 embeds service 1.32.0. Native SQLite-backed development is separate from production databases. Root coordinates immutable CLI checksum and private ownership before startup. Native official SDK 1.34.0 metadata declares nexus-rpc 1.4.0, protobuf/types-protobuf >=3.20,<8 and typing-extensions >=4.2,<5; no additional async pytest plugin is needed.

Next: root reviews the final owned diff/raw evidence, runs integrated offline guards, updates CURRENT/handoff and publishes only authorized tracked files. No additional native rerun is justified without source/boundary changes or a new unresolved concern. Select a separate bounded tracing or crash/interruption fixture before claiming more Milestone 3 coverage; keep actual OpenShell unknown dispatch and direct/durable agents behind their own qualified gates. No fallback time-skipping server or mock replaces a failed persistent-service gate.
