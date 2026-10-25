> Historical record. Commands, counts and status describe the recorded revision, not the current working tree. See [current work](../../README.md) for current guidance.

# Implementation audit and simplification

The supported Plan 1 pilot has real production paths for source admission, ADK producer/auditor episodes, Docker-native reference execution, Temporal investigation/evaluation, immutable operation reconciliation, final recording, external scoring, and CLI operation. No unfinished placeholder, canned passing response, mock provider selection, host-execution fallback, or test-module import was found in those production paths. Static regressions and installed-wheel inspection enforce part of that boundary.

That does **not** mean the entire broader architecture or arbitrary hostile-code verification is production qualified. The implemented scope remains `python.secret_disclosure/1` for authorized, standard-library Python targets on a disposable Linux host. Plan 2, arbitrary probes, dependency/build repair, other languages, application exposure proof, generic negative clearance, and durable artifact-host-loss recovery are intentionally absent, not simulated. The live security producer is still provider-policy blocked and has not been qualified. General hostile-interpreter observation authenticity remains a security-design limitation. Neither limitation was concealed with a mock or an alternate provider.

## Production versus test doubles

The installed CLI composes the real ADK Runner/model connector, Temporal Client/Worker and Docker SDK. Settings accept only the concrete Gemini or LiteLLM model connectors, and there is no CLI option for a scripted provider. A missing daemon, image, source capability, provider request, native report, coverage, artifact, or worker remains a failure or explicit uncertainty.

Tests deliberately contain scripted native `BaseLlm` instances, typed fake activities and fake sandboxes so error states, budgets and deterministic policy can be exercised without purchasing model calls or executing hostile code for every unit assertion. `model_override` is an explicit dependency-injection seam used by these labelled tests, not a production fallback. The wheel contains no test package. Genuine Docker/Temporal integration and real CLI-process tests are separate from scripted model accuracy. The real auditor smoke is separate again. A passing scripted producer is never reported as a successful live security investigation.

## Implemented simplifications

The ADK episode helper now consumes the native Runner event stream and retains only its last relevant non-thought text, rather than buffering all events and reverse-scanning them. Native callback parameters use the SDK's named/typed contract. The unused episode output-token parameter and redundant producer factory tool alias were removed. ADK still owns sessions, tool dispatch and event execution. Native `RunConfig(max_llm_calls)` remains alongside accounting callbacks because runner admission and accurate usage are different responsibilities. [1] [2]

CLI presentation uses Rich `Console`, `Status`, `Panel`, `Table`, `JSON` and `RichHandler`; there is no hand-written ANSI renderer or spinner implementation. Standard argparse remains the command parser rather than introducing a second CLI framework migration. Pydantic's `TypeAdapter` converts nested native receipts to JSON, so batch inspection does not require a custom recursive serializer. [3] [4]

Temporal's native `ActivityInboundInterceptor` supplies lifecycle logs across all activity types rather than decorating every activity with another custom logging wrapper. Native workflow queries expose real phase/round and completed/total values. `WorkflowHandle.result()` owns completion waiting; the CLI only observes queries for presentation. The final recording change uses native `workflow.patched` history compatibility and a 90-second schedule-to-close window covering queueing, retries and backoff. [5]

The CLI and activity now share one cancellation-safe `asyncio.to_thread` owner for Docker evidence. It waits for the owning native thread to remove containers before cancellation completes. This replaces duplicate cancellation logic and fixes the direct-reference path's cleanup asymmetry. One usage calculation is shared by scoring and human presentation, including producer **and** auditor calls and unknown totals after lost episodes.

Most remaining custom code is not replaceable SDK plumbing: source admission, random-fixture observation semantics, raw evidence conformance, immutable execution-intent identity, case/scope binding, and conservative disposition policy are Corsair's domain and safety rules. Removing them to lower a line count would weaken the system.

## Audit findings resolved

Source admission now opens the trusted root and every untrusted directory component through Linux directory descriptors with `O_DIRECTORY`, `O_NOFOLLOW`, no-follow metadata checks and relative `dir_fd` opens. It no longer follows a pathname after checking it. An event-synchronized directory replacement test rejects the swap without publishing an artifact; unsupported secure-FD platforms fail closed. This is not an atomic whole-tree filesystem snapshot: use an operator-created immutable checkout when that guarantee is required.

Saved positive/fix scores now bind the validated admitted case identity to the scored result. Batch scoring also rejects result/run identities that differ from their child receipt. Actual valid native evidence cannot be relabelled as another case to obtain a passing oracle.

The native driver now catches target-raised `BaseException` signals, including `pytest.Failed` and `SystemExit`, so the demonstrated attack of writing a fake disclosure marker and raising a pytest failure is recorded as a native error, not a violation. Real Docker regressions cover this. It does not solve arbitrary interpreter manipulation, process exit, monkey-patching or report tampering by a hostile target. The in-process observer remains unsuitable as universal hostile-target attestation; the threat model retains that blocker explicitly.

Investigation action admission and final result persistence now have explicit separate budgets. The final record has a 30-second attempt limit, at most three native SDK retry attempts and a 90-second total schedule-to-close bound. Submission/child workflow execution has the existing action-budget-plus-120-second outer timeout. Cleanup and finalization are not presented as part of the action budget or as proof that an uncertain operation ran.

## Operator interface

The CLI automatically uses human panels on a terminal and JSON when piped. Operators can select `--format auto|human|json`, disable colors or animation, choose log level/encoding, and mirror logs to JSONL. These controls work before or after commands. Human results show scope, reason, control/adversarial native outcomes and coverage, auditor decision, producer/auditor usage, model and artifact identities, and unknown cost rather than an invented figure.

`doctor` makes actual read-only SDK checks of directories, Docker daemon/image/runtime, Temporal namespace and workflow/activity pollers. It never substitutes a guessed health response, creates a directory, starts infrastructure, calls a model or verifies provider credentials. Poller presence is not an execution qualification.

`inspect --online --watch` detects the native workflow type and supports both investigations and evaluation batches. Spinners indicate waiting, not a fabricated percentage or security conclusion. Ctrl+C detaches the local waiting client and returns `130`; remote cancellation remains explicit. The native worker uses the SDK context and a 45-second graceful-shutdown allowance on SIGTERM.

Logs use standard logging and a scalar metadata allowlist, with run/activity identity, attempts, timing, phases, gates, usage and cleanup status. Known environment credential values, endpoint URLs and control characters are redacted. Raw SDK request diagnostics and exception locals are not forwarded. Logs and spinners are on stderr; JSON stdout remains parseable. Safe metadata can still be sensitive, so logs should be restricted and excluded from source control. Unknown usage/cost stays unknown.

See [CLI reference](../../../reference/cli.md), [pilot runbook](../../../operations/runbooks/pilot.md), [architecture](../../../architecture/overview.md), and [current handoff](../handoffs/HANDOFF-0139-cli-audit.md) for commands, receipts and limits.

## Next simplifications to consider, not placeholders

Continue with ordinary ADK activities and native Temporal durability until a measured need justifies turn-level integration. The experimental adapter would change recovery semantics and increase qualification work; it is not a minimal safe replacement today.

The ADK budget-stop bridge still touches its invocation context because the pinned callback context lacks a public forwarding termination setter. Keep this isolated and regression tested; replace it with the native public API when the pinned SDK supports it. Dropping accurate accounting or replacing bounded invocation behavior with another custom runner is not a simplification.

Broader production qualification requires an independent observer boundary and an operator-approved provider capable of the intended authorized workload, followed by human-labelled held-out evaluations. Those decisions need discussion; the CLI cannot diagnose them away, and small authored fixtures cannot establish population accuracy.

## References

[1]: https://google.github.io/adk-docs/callbacks/types-of-callbacks/ "ADK callback contract"
[2]: https://google.github.io/adk-docs/runtime/event-loop/ "ADK native event loop"
[3]: https://rich.readthedocs.io/en/latest/console.html "Rich native console and terminal detection"
[4]: https://rich.readthedocs.io/en/stable/logging.html "Rich standard logging handler"
[5]: https://docs.temporal.io/develop/python/workers/interceptors "Temporal Python native worker interceptors"
