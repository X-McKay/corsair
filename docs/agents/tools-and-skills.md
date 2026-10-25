# Tools and runtime instructions

Agent capabilities are deliberately smaller than the surrounding runtime. The producer receives two episode-private native ADK function tools; the auditor receives none. Factory metadata and construction reject a producer tool list that does not exactly match this approved surface.

| Role | Tool | Permitted operation | Boundary |
| --- | --- | --- | --- |
| Producer | `read_file(path)` | Read one bounded, normalized relative text file from the already admitted immutable source snapshot. | No arbitrary host path, write, execution, or new source admission. |
| Producer | `list_files()` | List bounded regular relative files in that same validated snapshot. | No archive mutation, shell, or target invocation. |
| Auditor | None | Review the supplied outcome-blind packet only. | No source reads, execution, network, or tool calls. |

The producer receives a read capability created for one `ProducerInput`; it cannot choose a host directory or obtain the broader source-admission capability. Tool output is bounded by the configured tool-output budget. Source content is untrusted data, so embedded instructions do not override the packaged role instruction.

## Not agent tools

The following are trusted runtime or evaluation components, not capabilities an agent can call:

- **Source admission and snapshot storage:** operator-owned local source admission creates a hash-verified snapshot before the producer reads it. The current SCM boundary is local snapshots, not a remote forge client.
- **Sandbox execution:** the trusted verifier invokes the configured Docker SDK sandbox with the operator-owned recipe. The sandbox never appears as a producer or auditor tool.
- **Artifacts, evidence, and disposition:** immutable artifact storage, receipt verification, and policy decisions are outside both agent contexts.
- **Temporal coordination:** workflows own durable rounds, activity scheduling, cancellation, and recording. Agents run only within the normal bounded activities.
- **Oracles and scoring:** frozen labels and external scoring are evaluator inputs. They are never provided to the producer, auditor, tools, or workflow packet.

There is no production MCP integration, skill loader, remote forge connector, generic tool catalog, or dynamically discovered tool directory in this package. Adding a development document does not install a runtime capability, and adding a runtime resource requires an implemented factory/metadata/validation change—not a directory convention.

## Runtime instructions versus development guidance

The model sees only the packaged system instruction associated with its role plus the bounded activity packet. The producer instruction requires a single structured `Submission`; the auditor instruction requires an `AuditResult` and forbids claims about execution or disposition. Those package resources are loaded by the role factories.

This documentation, repository development guidance, and evaluation procedures are for maintainers. They do not imply that a similarly named runtime skill, plugin, prompt directory, MCP server, or tool exists. For the role architecture and structured-output rules, read [the overview](overview.md); for changes, read [development](development.md); and for frozen checks, read [evaluations](evaluations.md). Current plans are available through the [plans index](../plans/README.md).
