# Contributing to Corsair

This is the detailed development workflow linked by the root contribution entrypoint. It governs current changes; active plans and historical records are indexed in [plans](../plans/README.md). Corsair is a bounded personal-use pilot, so a contribution does not imply deployment, issue closure, publication, or a broader security claim.

## Before changing code

Read the root overview, the relevant architecture/reference pages, and the active plan or issue. Check the branch and working tree, then preserve unrelated dirty files. Define one bounded objective, its owning package, accepted inputs/outputs, security boundary, and the smallest evidence that can test it.

Use the implemented package boundaries in [conventions](conventions.md). Contracts remain SDK-free and live once in `contracts/`; settings remain in [`src/corsair/settings.py`](../../src/corsair/settings.py); prompts/resources remain role-local; workflows coordinate only deterministic Temporal state. Do not introduce a remote SCM adapter, Bedrock adapter, HTTP service, second scheduler/agent loop, generic repair framework, host execution path, or placeholder backend without separately authorized implementation and qualification.

A change that affects a schema, setting, prompt, budget, source admission, image/runtime, policy, model, evidence verifier, workflow, package resource, or evaluation must state the affected consumers and required gates. Link the authority instead of copying a changing schema/configuration into a new document.

## Implement and test in a bounded loop

1. **Implement.** Change the smallest cohesive component. Keep model outputs typed through native ADK `output_schema`; preserve ordinary Temporal activities and immutable evidence identities. The producer remains limited to `read_file` and `list_files`; target code remains in the configured Docker sandbox.
2. **Test.** Run the nearest unit or integration tests, then affected consumers. Before delivery run `just check` and the appropriate offline, Docker, Temporal, package, and evaluation gates described in [testing](testing.md). Use strict warning handling (`-W error`) for a qualification command and report skips/deselections rather than calling them passes.
3. **Evaluate when agent behavior changes.** Freeze inputs and keep oracle labels outside agent/workflow packets. Compare the role against its own baseline before composition. Scripted ADK, live isolated-agent, native Docker/Temporal, and whole live-chain evidence answer different questions and must be reported separately.

Do not evade a provider policy decision, weaken TLS/sandbox/resource/cleanup controls, run an untrusted target on the host, change an oracle or frozen fixture to hide a failure, or automatically replay an uncertain operation. Preserve unknown telemetry as unknown.

## Final implement–test–cleanup–retest–package sequence

Before declaring a bounded change ready, complete this order:

1. **Implement** the reviewed change and update its plan with decisions and intended checks.
2. **Test** the changed boundary and affected consumers; keep failed/unrun gates visible.
3. **Clean up** only generated files and temporary resources created by the work. Confirm Docker cleanup through immutable identity/receipts; do not delete another contributor's files, committed evidence, an uncertain intent, `.runs` data needed for diagnosis, or an active plan to obtain a clean result.
4. **Retest** after cleanup, including `just check` and the same relevant strict test/evaluation commands. Reinspect any interrupted Docker/Temporal work instead of assuming cleanup or completion.
5. **Package** with `just build`. The offline suite's package test also builds the distribution, installs the wheel into a fresh environment outside the checkout, and verifies packaged resources and the console entry point. Run it whenever a package resource, layout, dependency, or entrypoint changes.

Do not invent an automated archive/record-moving recipe. When work actually completes, update the bounded plan and its links according to [plans](../plans/README.md), retaining commands, actual results, failures, and unrun gates as historical evidence.

## Review and record quality

Review the concrete security and ownership boundary, not only style. Check that contracts do not import vendor SDKs; ports do not import adapters; workflows do not perform I/O; operator-controlled budgets/policies remain non-agent-editable; source/evidence/result identities still bind; and logs do not disclose prompts, source content, payloads, secrets, endpoints, or raw provider material.

A static dead-code scan is a candidate list. Validate callers, registered activities, SDK callbacks, Pydantic validators, resource metadata, and serialized schema compatibility before deletion. Keep functions focused and explicit rather than splitting a coherent ownership boundary into one-line wrappers or adding speculative abstractions.

In the active plan, record the revision/context, scope, commands, actual outcomes, platform/service prerequisites, skips, warnings, failures, cleanup confirmation, and remaining uncertainty. Historical handoffs and archived records explain prior revisions; they are not current instructions or proof for an untested local change.

## Contribution hygiene

Keep secrets in the worker environment. Never commit `.runs/`, `.state/`, `.env` files, credentials, private diagnostic exports, raw model reasoning, raw provider responses, build caches, or generated distributions. Use relative documentation links and repository-root-relative shell commands. Keep claims bounded: current small diagnostics and native qualification do not establish production readiness, hostile-target integrity, application-wide exposure, negative clearance, or population-level model accuracy.

The project has no project-wide license grant at present. Do not add license terms through a contribution; see [LICENSE](../../LICENSE) for the current status.
