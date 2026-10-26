# Development conventions

These conventions apply to current implementation work. They describe how to preserve the architecture; exact schemas and settings remain authoritative in source and their reference pages. Read the [architecture overview](../architecture/overview.md) for system context and [plans](../plans/README.md) for active decisions and historical evidence.

## Keep ownership explicit

| Location | Owns | Do not use it for |
| --- | --- | --- |
| `agents/` | Role-local ADK factories, instructions, metadata, and private tools | Shared contracts or a general agent framework |
| `contracts/` | Canonical SDK-free Pydantic models | Vendor SDK types or duplicate wire models |
| `ports/` | Narrow domain interfaces over contracts | Adapter imports or provider registries |
| `adapters/` | Implemented ADK, local source, Docker, filesystem, and Temporal integrations | Unimplemented remote-SCM, Bedrock, or HTTP placeholders |
| `entrypoints/` | CLI, typed Python API, worker, diagnostics, and terminal presentation (`terminal.py` dispatch, `render/` views) | A second scheduler or workflow engine |
| `workflows/` | Deterministic Temporal coordination | Filesystem, model, network, or Docker I/O |
| `steps/` | Ordinary activities, evidence verification, manifests | Alternative durable orchestration |
| `policies/` | The pure kernel: gate order, verdict table, fix decisions and risk material | Trusted observation generation |
| `observability/` | Sanitized lifecycle logging | Prompt, payload, source, or provider-content logging |
| `evaluation/` | Isolated-agent evaluation and external scoring | Oracle data in an agent or workflow input |

Use concrete composition for real consumers. Add an abstraction only when a second qualified consumer demonstrates it; do not add a generic graph, scheduler, retry broker, dependency-injection container, provider protocol, or repair framework.

## Preserve the native execution model

Google ADK owns each fresh producer or auditor episode. Its factories use the canonical `ProducerDecision` and `AuditResult` Pydantic models (proposals retain `Submission`/`PlanRevision`) through native `output_schema`; do not restore string-to-object repair or a custom submission state. Native callbacks account for model/tool calls and constrain per-episode budgets.

Temporal owns durable rounds, deadlines, cancellation, activity retries, and recording. Workflows coordinate deterministic state only; ordinary activities perform ADK, source, Docker, and storage work. Do not substitute an upstream Google ADK Temporal integration for the implemented ordinary-activity model, or claim that an interrupted model call resumes mid-episode.

The producer receives only the episode-local, read-only `read_file` and `list_files` tools and the skills toolset over an admitted immutable snapshot. The auditor has no tools, is outcome-blind, and can only reject. Models propose JSON payload pairs only; the kernel materializes the recipe, runs the differential pair, checks exact target-line coverage, and decides the label in code. Oracles remain evaluator-owned and outside agent, tool, and workflow packets.

## Treat identity, evidence, and cleanup as part of behavior

Admit only local source trees into immutable, bounded snapshots. Descriptor/no-follow support is required; there is no pathname-walking fallback, remote checkout, or host target-execution path. Source, submission, configuration, prompt, image, budget, and operation identities are recorded as digests or immutable references. An existing intent without a reconciled observation is uncertain and must not be automatically replayed.

The Docker SDK is the only supported target-execution adapter. Preserve the configured read-only, offline, resource-limited container boundary and cleanup verification bound to immutable container identity. A native error, skipped test, denied sandbox, unknown cleanup state, or missing artifact is not a passing result and never authorizes a negative security claim.

Artifacts are content-addressed and immutable. Read and validate references rather than overwriting a result to make a run look complete. Local artifact storage does not survive host loss by itself; do not represent Temporal history as a replacement for the artifact store.

## Code, schema, and configuration discipline

Keep functions small and named for one ownership boundary. Prefer real annotations and explicit runtime narrowing to broad type ignores. A static dead-code report is a review lead, not deletion authority: SDK callbacks, Pydantic validators, registered Temporal activities, metadata fields, and wire-schema members can be dynamically live.

Treat `contracts/` as the single schema authority and [`settings.py`](../../src/corsair/settings.py) as the settings authority. Documentation should link to those sources or a maintained reference instead of copying a changing field list or default. A configuration change must not become a secret-bearing example; credentials remain in the worker environment.

Run the maintained gate before delivery:

```bash
just check
```

It executes `ruff check src tests evals scripts`, `ruff format --check src tests evals scripts`, `just --fmt --check`, and `ty check --error-on-warning`. Ruff intentionally excludes `evals/fixtures`: formatting frozen target inputs could change declared line numbers and canonical source hashes. That exclusion is not a waiver—typing and native conformance still cover them.

## Records, limits, and safe changes

Keep a bounded plan current with scope, decisions, commands, actual results, blockers, and unrun gates. Link it through [plans](../plans/README.md); work records are records, not an alternate source of runtime behavior.

Keep lifecycle output sanitized. JSON command results stay on stdout; logs contain allowlisted operational metadata only. Never commit `.runs/`, `.state/`, credentials, endpoint secrets, raw provider responses, raw model reasoning, or private diagnostic exports. Preserve a policy block or operational failure as attributable evidence rather than changing TLS, policy, source admission, Docker isolation, or target choice to obtain a pass.
