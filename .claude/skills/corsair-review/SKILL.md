---
name: corsair-review
description: Use when reviewing a Corsair design, code, PR, prompt, skill, policy or SDK change. Check purpose, native reuse, domain boundaries, evidence validity, evaluation coverage and truthful operational claims.
---

# Corsair review

Read `AGENTS.md`, changed files and the relevant work record. Use SPEC-0082 as the current v2 architecture, not historical v1 role or migration instructions. Review the actual behavior; this is not another approval ceremony.

1. **Scope and simplicity:** Verify one concrete objective and acceptance criterion. Remove unrelated changes, duplicated rules and speculative abstractions.
2. **Native reuse:** Check pinned SDK support before accepting maintained wrappers. Retain justified domain contracts; do not replace them with unrestricted generic capabilities.
3. **Boundaries:** Check typed ports, explicit provider/mode selection, tools, policy authority and consumer compatibility. Reject silent fallback and unqualified runtime claims.
4. **Security evidence:** Preserve exactly two native probes through the real seam, independent authors, frozen artifact binding and outcome-blind review. Check source linkage, benign/adversarial input, relevant non-vacuous assertions, cited production/test lines and dependency-double limits. Passing authored assertions alone do not establish validity.
5. **Failure attribution:** Distinguish provider, policy, dependency, transport, uncertain command delivery, native test and cleanup failures. Missing evidence must not prove an application fix. Do not retry uncertain side effects or weaken operator policy.
6. **Evaluation:** Check the changed agent in isolation. Report mode, language, frozen input/release identities, repeat count, completion and evaluator coverage, semantic quality, trajectories and observed tokens/latency. Keep scripted, live-model-fixture, native-workspace and durable qualification distinct. Never treat null telemetry as zero.
7. **Operations and handoff:** Check CLI text/JSON and cancellation behavior at the changed boundary, record actual failed/unrun tests, update living docs and preserve historical handoffs. Verify the post-cleanup re-test.

Fix concrete authorized findings, rerun affected checks and record unresolved limits. Do not turn structural checks into a blanket safety guarantee or require disclosure of private model reasoning.
