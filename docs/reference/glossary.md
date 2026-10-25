# Glossary

This glossary is a short vocabulary guide. Canonical fields, validation, and enum values remain in the [domain schema reference](schemas.md).

| Term | Meaning in Corsair |
| --- | --- |
| **Artifact** | Immutable bytes held by the artifact store. An artifact is identified by an [`ArtifactRef`](schemas.md#prepared-case-manifest-and-artifacts), not by a mutable host path. |
| **Artifact reference** | The digest, byte size, and media type used to retrieve and verify immutable stored bytes. It is not itself evidence of a security conclusion. |
| **Audit** | The outcome-blind auditor's structured semantic review of a submission. It has no tools, never sees an outcome, and can only reject; it cannot create native evidence or assign a label. |
| **Budget** | Bounded per-investigation limits for rounds, model/tool calls, output, elapsed/probe time, and source/tool bytes. It belongs to a request, not a case. |
| **Case** | The stable investigation description: finding, local source, recipe, optional fixed source, and `case_id`. It does not include an execution budget or run identity. |
| **Label (verdict)** | The kernel's conclusion in an `InvestigationResult`: `EXPLOIT_DEMONSTRATED`, `EXPLOIT_NOT_DEMONSTRATED`, `INCONCLUSIVE`, `UNABLE_TO_RUN`, or `ERROR`. It is decided by code after the gate order, and is distinct from operational execution status and individual role outcomes. |
| **Execution status** | The operational state recorded with a result: `COMPLETED`, `BLOCKED`, `ERROR`, or `CANCELLED`. A completed workflow can still have an inconclusive disposition. |
| **Finding** | The reported claim and its location/scope. It is an input to investigation, not verified evidence. |
| **Fix / fixed source** | An optional separately supplied local source revision. Its observation produces a fix status for the admitted demonstration, not a general patch certificate. |
| **Fix status** | `NOT_REQUESTED`, `DEMONSTRATION_BLOCKED`, `NOT_BLOCKED`, or `UNVERIFIED`. It describes the fixed-source observation and must be read alongside its evidence. |
| **Manifest** | Run provenance binding request/configuration/prompt digests, image identity, model names, and capabilities. It is not a live configuration file and contains no credentials. |
| **Observation** | A trusted verifier record for a concrete control/adversarial operation, including digests, optional role outcomes, immutable receipt reference, feedback, and cleanup confirmation. It is not an agent submission or final verdict. |
| **Plan revision** | The producer's bounded proposed reasoning/next-step record within a `Submission`. It is not a Temporal plan, scheduler, or execution history. |
| **Prepared case** | The worker-derived form after source admission: the case details plus immutable snapshot references, bounded excerpt, and manifest. |
| **Producer** | The bounded ADK role that proposes one typed `Submission` holding a benign/exploit payload pair. It may only read/list files from an already admitted snapshot and load packaged skills; it does not execute the target, write a probe, or author assertions. |
| **Recipe** | The operator-owned test shape for a target seam. It fixes the callable, fixed arguments, fixtures, expected control behavior, and exception policy; the kernel materializes it with the proposed payloads, and the producer proposes only payload values. |
| **Request** | An `InvestigationRequest`: a case plus its bounded budget. It is the typed input to the durable investigation workflow. |
| **Role outcome** | A verifier-level observation for a control or adversarial execution: `PROPERTY_HELD`, `VIOLATION`, `INVALID`, or `ERROR`. It is neither an execution status nor a disposition. |
| **Run ID** | The unique Temporal workflow identity supplied separately from `case_id` for an investigation. Duplicate IDs are rejected rather than reused or attached. |
| **Source admission** | Worker-side, descriptor-checked acceptance of a local directory under configured `source_root`, followed by an immutable snapshot. Request-path normalization is not admission. |
| **Submission** | The producer's typed hypothesis, plan revision, and exact control/exploit values for the recipe's payload parameter. Structured validity does not prove semantic correctness or a vulnerability. |
| **Temporal workflow** | The durable coordinator of bounded rounds and result recording. It is distinct from the native ADK agent episode and from Docker target execution. |
| **Worker** | The process that polls the configured Temporal task queue, composes activities, and holds provider credentials in its environment. It is not an HTTP server. |

For typed use and await behavior, see the [Python API reference](api.md). For configuration and worker credential boundaries, see [configuration](configuration.md). For current terminology- or contract-related work, see [current plans](../plans/README.md).
