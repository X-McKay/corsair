---
name: corsair-review
description: Use when reviewing a Corsair design, implementation, PR, prompt, policy, runtime, or SDK change. Check simplicity, native feature reuse, component boundaries, evidence validity, appropriate evaluations, and accurate qualification claims.
---

# Corsair review

Read `AGENTS.md`, the changed files, and the relevant spec/plan/contract. Review the final behavior against the current scope. This is a review checklist, not another required approval meeting or a request to spawn agents.

1. **Purpose and scope:** Does the change satisfy a concrete objective? Are acceptance criteria and exclusions clear? Are unrelated changes or speculative abstractions removable?
2. **Dependencies:** Could the selected SDK/service provide the capability directly? Are new services, shared utilities, agents or repair loops justified by an observed need? Are actual pins/capabilities verified?
3. **Boundaries:** Are ports narrow and vendor objects confined to adapters? Are modes/providers explicit? Does a local change stay local, or are consumers/invalidation rules updated? Is there any silent fallback?
4. **Evidence and security:** Can errors be attributed to the correct layer? Are command delivery and cleanup identity handled correctly? Could a missing endpoint, skipped test, sandbox denial, failed control or invented output produce an unsupported conclusion? Are credentials and trusted records confined?
5. **Unit-test validity across languages/frameworks/CWEs:** Are exactly the control and security tests authored through existing real application seams by default? Do they exercise the intended immutable source and reported condition, with relevant assertions? Do dependency doubles preserve the production logic under test and limit claims to the measured property? Is integration justified by the property? Are optional witnesses behavior-preserving and coverage-bounded? Missing low-level telemetry alone must not reject a valid unit test; a passing generated assertion alone must not admit an unsupported conclusion.
6. **Testing and evaluation:** Do checks exercise changed behavior and required negative paths? For agents, are trajectory/consistency and other relevant dimensions considered with isolated cases and observable metrics? Are fixture, render, live and durable coverage distinguished?
7. **Operations and continuity:** Are latency, calls, tokens, retries and unknown coverage visible where relevant? Are docs, work records, current gate and handoff accurate? Are failure and recovery paths inspectable without additional frameworks?

Record concrete findings with file/record references and impact. Fix authorized findings, rerun affected checks, and update the plan. Report unresolved findings and unavailable checks plainly. Do not turn a checklist into a blanket safety guarantee, prescribe private model reasoning, or require the user to reapprove already authorized work.
