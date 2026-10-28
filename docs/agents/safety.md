# Agent safety boundaries

The [security policy](../../SECURITY.md) and packaged [risk assessment](../../src/corsair/policies/risk.md) remain authoritative. This is a personal-use pilot with bounded native conformance, not general hostile-source integrity or production qualification.

Intake never executes target code. It normalizes one issue, reads admitted source in the inspection container and selects only from currently available operator-permitted images. Issue fields cannot choose host source paths or grant permissions.

New v3 investigations allow producer-authored code and commands only as bounded `TestPlan` proposals. A separate outcome-blind auditor reviews semantic relevance. Trusted execution materializes tests and invokes commands only inside the configured Docker sandbox. The host never imports or runs target/test code. Read-only source, non-root execution, no network, no credentials/socket, resource limits and immutable-ID cleanup remain enforced.

Models cannot supply environment variables, mounts, registry addresses, Docker security settings or their own observations. Arbitrary generated reports, assertions and exit conventions remain untrusted. Native receipts establish which processes ran and their actual exits/output, with truncation and uncertain cleanup explicit. Neither accepted audit nor successful exit establishes the claimed vulnerability. Security assessment remains `UNRESOLVED`; failure never grants negative clearance.

Evaluator oracles stay outside role, tool and workflow packets. Source/tool content is untrusted data and cannot expand capabilities. Fixed-source comparisons reuse the exact accepted plan in a fresh admitted environment and do not prove broad patch effectiveness.

The historical v1/v2 path remains JSON-payload-only under its fixed observers. That earlier restriction applies to archived diagnostics, not the explicitly authorized v3 sandbox test-plan capability. Recorded old semantics and fixture labels are preserved.
