# Native Temporal fixture foundation qualification

This is a bounded independent Milestone 3 fixture result under [SPEC-0013](../development/specs/SPEC-0013-temporal-fixture-foundation.md) and [PLAN-0015](../development/plans/PLAN-0015-temporal-fixture-foundation.md). [Runbook](../runbooks/temporal-fixture.md) contains repeatable native commands. No OpenShell sandbox, model/provider call, agent integration or application security finding was involved.

## Selected tuple and native boundary

Python 3.12.13, Temporal Python SDK 1.34.0, and stable Linux amd64 CLI 1.9.1 with embedded service 1.32.0 were used on the actual host. [Runtime pins](../../deploy/temporal/runtime-lock.yaml) and `uv.lock` hold immutable acquisition/dependency identities. Official CLI archive SHA256: `09a0326a51db84d02735e53542b9ebd8c4758daf47482a9ab0abce15844e60d5`; extracted binary SHA256: `712217694cac9f786a72d4b6c876cd15f3dcf1bf31434d9fed6af25242a327a0`. Root verified the official release checksum before extraction; the executing harness rechecked binary bytes before startup. PydanticAI/Evals 2.55.0 is in the compatible shared environment but no agent runs durably in this qualification.

The native `server start-dev` bound loopback gRPC 17333, HTTP 17334 and metrics 17336, headless, with an exclusive private SQLite file. No container/cluster, service-policy alteration, SQLite pragma or mocked transport substituted for the service. SDK Worker, activities, child workflows, retries, query/signal, cancellation, default conversion and Replayer were exercised directly.

## Cases and evidence

The final reviewed candidate, `native-004`, passed **14 checks in 3.41 seconds**: eight offline checks and six actual service cases. Separate Python checkpoint processes passed preparation in 0.314 seconds and resume after actual service restart in 0.414 seconds. Parent run `01a12e29-7e2e-7f39-bcec-8ec8f3a73114` and child run `01a12e29-7e61-79a1-9c7a-f0b6661852ae` preserved the original pending histories, completed once, and replayed. Fourteen final actual histories were exported/replayed: 12 Completed and two Cancelled. `pending-parent.json`/`pending-child.json` preserve the pre-restart prefixes.

The before-live freeze records 13 inputs: owned workflow/test Python, shared `pyproject.toml`/`uv.lock`, runtime pins and Makefile. Its SHA256 is `36d1d59074a4146ba005cef942780cfd4ce4880fc5d5190816dd74d64dc0a1c1`. Full frozen bytes and manifest are retained under `native-004/source/` and `source-freeze.json`; all 13 then-current input hashes were checked after the run and matched. Final staged review subsequently removed one extra trailing blank line from `tests/temporal/support.py`: that one current file now differs only by EOF whitespace; the other 12 match. Native qualification remains attributed to the exact preserved frozen source; this formatting correction changes no behavior and did not trigger a live rerun. Documentation updates follow the qualification and are not falsely included in that pre-run freeze.

| Case | Required native observation |
| --- | --- |
| Success | One preparation and one completion activity; bounded literal result |
| Transient preparation | Native activity reaches attempt 3 under bounded retry policy; one completion |
| Permanent preparation refusal | Native nonretryable failure, one preparation attempt, completion not scheduled |
| Unknown completion fixture | One nonretryable completion failure becomes visible unknown; no output or resubmission |
| Parent cancellation | Waiting child and parent histories end Cancelled; completion never scheduled |
| Graceful worker replacement | Fresh Worker restores child history; completed preparation is not repeated |
| Persistent service process restart | Separate probe processes admit original pinned parent and child runs/history prefixes from the same SQLite database, then complete once |
| Replay | Actual final parent/child histories replay with the same source/SDK, without activity execution |
| Offline bounds/contract | Eight native ActivityEnvironment/conversion/schema/evidence-preflight checks |

All payload cleanup is `not_required` because the inert fixture activities allocate no external resources. Native service process cleanup is a separate measured requirement. The unknown case **simulates** uncertainty through an explicit fixture error; it does not qualify an external dispatch receipt, reconcile a command or prove safe OpenShell retry.

Original native-004 service PID 669873/start ticks 49542108 and restarted PID 670298/start ticks 49542658 were bound to the verified binary and the same private SQLite path. Both original Popen objects reaped with exit 0 after graceful termination, original `/proc` identities were absent and all three selected loopback endpoints were closed. Measured process lifetimes were 5.501/1.730 seconds. The original database stays private; no service remains running.

Root verified final current/frozen hashes, JUnit, command exits, same database and cleanup receipts. An independent sibling agent also audited all 13 frozen/current input hashes, seven parent/child run links and policy/result histories, both original persistent history prefixes, preparation/completion/signal counts and original service identities/absence/endpoints; no blocking finding remained within this scope. Its private audit is retained at `.runs/parallel-foundations-20261011/openshell-agent/temporal-native004-audit.json`.

Integrated offline repository guards passed `UV_OFFLINE=true make test-config`: 182 checks / 5.03 seconds, with one separately attributable PydanticAI `run_sync` deprecation warning. That broader result does not increase this native durability envelope.

## Retained failures and prior attempts

Private evidence root is `.runs/parallel-foundations-20261011/temporal-agent`; it is ignored and must not be committed.

- Initial sandboxed official metadata fetch failed DNS; research continued through official web sources and root-managed authorized acquisition.
- First service harness attempt failed `socket()` with EPERM before any native service creation. Its original `service-harness.log` is retained; the same explicitly owned loopback operation proceeded through authorized escalation.
- `native-001`: actual service suite passed 13 checks / 3.40 seconds. Separate-process resume completed the fixture, then failed its probe assertion because an untyped reconnected Client handle returned a dictionary. Native typed `get_workflow_handle_for` fixed the probe; no workflow retry/runtime change was needed. Both original services exited 0, with original process absence and endpoint closure receipts retained.
- `native-002`: corrected native suite passed 13 / 3.41 seconds and separate-process persistent resume/replay passed. Subsequent review strengthened nonempty original child history admission.
- `native-003`: 13 / 3.41 seconds and persistent restart passed with original child history-prefix admission, source/dependency/runtime-pin freeze and confirmed original process cleanup. Independent review then requested both parent/child pinned histories and evidence reuse refusal before dispatch. No earlier attempt's logs, histories or SQLite file were overwritten.
- `native-004`: final 14 / 3.41 seconds and separate-process original-parent/child restoration/replay passed after those review fixes. Reused `prepare` evidence refuses before native connection/dispatch; final history exports use exclusive writes. The successful result and cleanup are independently auditable under this attempt directory.

## Coverage and limits

The first scoped foundation demonstrates the listed fixture behavior with a real local native development service. It does not complete Milestone 3. Service stops are graceful process termination/reap; Worker replacement is graceful shutdown followed by a fresh native Worker. Neither is host crash, worker death during a dispatched activity, lost completion or storage-fault durability. Cancellation occurs at a deterministic waiting barrier before completion, not during external execution. Same-version replay is proven only for the saved fixture histories; cross-version compatibility remains unqualified.

The suite records workflow/run/event identities, final statuses, fixture attempt counts, JUnit duration and service process ownership/elapsed time. There are no model/provider/OpenShell calls by construction. No supported tracing exporter was configured or qualified; native RPC/poll/internal retry counts, queue/backoff timing, CPU/RSS and telemetry delivery remain unknown. A listening metrics endpoint alone is not tracing/metric qualification.

Production authentication/TLS/service databases, resource cleanup, artifact reference durability/invalidation, real external unknown delivery, native PydanticAI direct/durable equivalence and full investigation composition remain explicit future gates. General OpenShell transfers remain independently blocked by ISSUE-0006.
