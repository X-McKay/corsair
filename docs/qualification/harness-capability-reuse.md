# Native Harness capability reuse

This audit covers Pydantic AI Harness 0.55.0 with Pydantic AI core 2.55.0. It qualifies host fixture behavior, not model correctness, Temporal service replay, OpenShell execution, or a deployed environment. Existing frozen evaluations remain evidence for their original source versions.

## Adopted native boundary

All seven production factories attach native `LocalWorkspace(Path(__file__).parent, read_only=True)` and Harness `Skills('skills', include={role_skill_id})`. The two probe authors also attach the shared trusted probe skill library. These are operator-packaged directories; investigation source remains available through each role's existing typed ports. Native `AgentSpec.from_file` and `Agent.from_spec` continue to assemble the agent; the operator selects the model and budgets explicitly.

Skills reads the selected library at the start of every run. The first model offer contains the selected names and descriptions. Native `load_capability` supplies the selected instruction body on demand. The loaded capability is instruction-only: bundled files are neither loaded nor executed. Skill frontmatter does not grant tool authority. The explicit domain toolsets remain the tool authority, with no FileSystem or Shell capability attached.

`LocalWorkspace` is a working directory, **not host filesystem isolation**. Absolute and parent paths remain possible through the workspace API. `ReadOnlyWorkspace` denies writes, directory creation, removal, and command execution; it permits reads. Here the model has no general workspace file/path tool: Skills uses fixed trusted roots and the model selects catalog IDs. OpenShell remains the authority for admitting and executing untrusted investigation work; a local skill workspace is not an OpenShell substitute.

## Temporal semantics

Use the primary `ctx.workspace` route. Harness 0.55.0 explicitly documents secondary `Skills(workspace=...)` workspaces as in-process only; a durable engine does not route them through workflow machinery. The factories therefore do not use that argument.

Core `DurableWorkspace` routes primary workspace operations issued in workflow code through the native workspace operation. Its initial `ensure` is synchronized once per run; later operations carry the workspace ref. Inside durable activities, workspace operations run directly against the reattached backend. The Temporal transport serializes the run context, workspace ref and typed call and restores them for the activity. Expected workspace failures cross as result data and are re-raised with their original type, including read-only denial. Backend access from workflow code is rejected to prevent bypassing durability.

Runtime Skills capabilities are instruction-only, which matches native durable runtime capability restrictions. Worker package paths must remain stable and contain the same packaged bytes for a retained workflow history; this audit does not demonstrate replay across changed worker packages.

## Candidates and retained boundaries

| Native capability | Decision and concrete boundary |
| --- | --- |
| Skills + primary LocalWorkspace | Adopt for trusted role procedures; preserve narrow explicit domain tools. |
| FileSystem / Shell / composite Coder | Not attached in this first adoption. Next, compare restricted native FileSystem with source/planning read ports and own-file authoring, and native Shell with preparation/execution ports. Admit a replacement only after immutable source identity, path/operation restrictions and native receipts are preserved. LocalWorkspace is not sandbox isolation; untrusted execution still requires the admitted OpenShell boundary. Full Coder defaults are unnecessary for the narrow roles. |
| ToolOutputLimits | Evaluate separately if needed. Truncation, spill files, and optional summarization change the evidence presented to the model and can add storage authority or model calls. They do not replace exact typed observation receipts without measurement. |
| SpendLimits | Potential operator spend accounting across runs. Existing native UsageLimits and stage ceilings still govern each run; shared counters and price completeness need a demonstrated requirement. Unknown usage remains unknown. |
| Guardrails / SystemReminders | Available native hooks, not replacements for deterministic admission or immutable source-bound validity review. A model judgment cannot establish a security fix. |
| Planning / subagents / DynamicWorkflow | No demonstrated need in the fixed independent control-then-exploit graph. Domain planning already has typed inputs and outputs. |
| Compaction / history transforms | Require isolated evaluation before adoption: source grounding and attributable current-run observations must survive any transformation. |

The small existing native hooks remain: tool budget preparation withdraws domain function tools at the configured cap, and prompted-output handling preserves provider detail while rejecting ambiguous JSON output. Harness capabilities are not assumed equivalent to those behaviors. No new scheduler, workspace backend, credential machinery, language parser, or generic repair loop is introduced.

## Host checks and limits

`tests/agents/test_harness_skills_isolation.py` exercises the installed SDK with FunctionModel and temporary trusted libraries. Concurrent runs start with unloaded instruction bodies, load only the included skill, and offer only native `load_capability`; sibling bodies and bundled code are not exposed. Read-only mutation and command attempts fail without changing the filesystem. Native DurableWorkspace calls use a host double for Temporal activity dispatch, with one synchronized ensure, two real reads, and a transported write denial.

Receipt: `PYTHONPATH=src:. /tmp/corsair-pr-review/venv/bin/python -m pytest -q tests/agents/test_harness_skills_isolation.py` — **3 passed in 0.38s**, offline host execution. The restricted runner stalled before producing results; the same checks completed on the host. The host dispatch double establishes native operation behavior, not a Temporal server history or replay result. Affected checks including `tests/agents/test_native_agent_specs.py`: **16 passed in 1.06s**. An offline `uv build --offline --wheel` succeeded; all 18 packaged native manifest/skill assets and policy YAML byte-matched current source. `git diff --check` passed. Live provider, Temporal service, and OpenShell qualification remain separate gates.

Pinned installed source inspected: `pydantic_ai_harness/skills/_capability.py`, `skills/_loader.py`, `_workspace.py`; core `capabilities/local_workspace.py`, `workspaces/readonly.py`, `durable_exec/_workspace.py`, and `durable_exec/temporal/_transports.py`.

Primary upstream guidance: [Harness Skills](https://github.com/pydantic/pydantic-ai-harness/blob/v0.55.0/docs/skills.md), [Harness Shell](https://github.com/pydantic/pydantic-ai-harness/blob/v0.55.0/docs/shell.md), and [Pydantic AI workspace documentation](https://ai.pydantic.dev/workspace/). Installed pinned source governs this audit when current documentation differs.

Native reserved `load_capability` remains offered after `PrepareTools` withdraws domain tools. It counts toward native usage: a second activation under `UsageLimits(tool_calls_limit=1)` is refused before execution. The focused regression checks exactly one native capability return and no second body disclosure; do not describe withdrawal as hiding every SDK tool. Native usage can include proposed calls that caused refusal; it is not a count of successful executions.
