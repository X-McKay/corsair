---
id: HANDOFF-0072
kind: handoff
title: Environment host evaluation review
status: recorded
updated: 2026-10-13
related: [SPEC-0029, SPEC-0044, PLAN-0048]
---

# Environment host evaluation review

## Verified state

Base 6be1b5f55224cbf97dc03a89f8c8a29d79f19df4. Resolve final commit with git;
PLAN-0052 and SPEC-0048 describe scope, failures and limits. Production environment prompt/skill
remain unchanged. Native host evaluation uses synthetic SandboxExecution observations; no setup
command or model-written code executes. Final scripted 16/16 passed; live provider unrun.

## Continuation prompt

Read AGENTS.md, CURRENT.md and PLAN-0052; verify branch/source and evidence. Review frozen
host fixtures and production contracts. Next bounded action is independent held-out semantic
cases or an explicitly configured provider baseline. Do not count synthetic setup observations
as sandbox/runtime qualification. Preserve .runs outside Git and retain failed evidence.

## Validation and blockers

Affected 62 tests passed. First guards run 993 passed/1 failed due to missing record template
sections; corrected and rerun. Provider and native runtime checks unrun, with no cleanup needed.

## Decisions and next steps

Keep environment-v1 unchanged until independent semantic measurement supports improvement.
Current authorization permits root publication; this lane commits locally only.

Corrected repository guards 994 passed; final native eval 16/16 clean,14 assertions per attempt.
Metric means retain compatibility and now expose sample coverage denominators; unknown metrics
are not zero. Missing report comparisons are unavailable rather than falsely zero failures.

Root review corrected evaluator outcome leakage from policy identity: all inputs now use
setup-public and fixture ids stay in HostInput, never agent prompts. Manifest renewed;
post-correction16/16 passed, final focused65 passed. Live requests remain unrun.

Follow-up cross-review closes inverted unsupported-runtime eval false positive using curated
oracle-only wording patterns. Fresh manifest, Make 16/16 with 15 assertions and focused 71 passed.
Root full suite 997 passed at preceding6f35dd3. Semantic wording coverage is deliberately bounded.


PR57 review follow-up, base `a1d44c3`: PLAN-0052 records reproduced metric/trajectory
false positives and their corrections. Blocked outputs must carry the curated command prefix
through their failure, unknown-delivery halt or operator cap. Shared summaries retain explicit
measured-zero attributes once while preserving absent telemetry as unknown. Four new regression
tests include blocked-build omission/reordering, unknown halt and budget halt negatives.
Affected suite70 passed; unchanged frozen host set16/16 at
`.runs/evals/environment/20261013T100728Z-development-scripted`, compared with prior
16/16. Command mean is now correctly1.75 with16/16 samples, output corrections0.0 with
16/16 samples. Current authorization permits updating/pushing this existing PR57 branch;
root owns review publication. `make test-config`:1050 passed; workflow guards5 passed; existing shared-runner lint findings are retained in PLAN-0052. No live requests,
setup execution or infrastructure calls. Resolve final source via Git rather than this snapshot.


Provider-coverage review follow-up (2026-10-13): a new regression reproduced missing and
partial provider token totals being counted as complete samples. The shared summary now
excludes native and observed input/output token metrics when provider_usage_present is false,
while preserving genuine zero counters, known token observations and scripted estimates.
The regression failed before the fix and passes after it; 23 affected checks passed.
Unrecorded fixture commands now identify their exit 126 response as synthetic and appear in
the attempt receipt under unrecorded_commands. The README explicitly limits live scores to
curated argv adherence. No provider or infrastructure was invoked. The first attribution
edit missed the fallback insertion and failed one test; corrected before the passing suite.
Main f6a87d6 (PR58) merged cleanly. Frozen host-only Make remains 16/16.
Full offline make test-config: 1056 passed, one existing SDK warning (52.48 seconds).
Independent read-only follow-up: four targeted regressions passed, no blocker found.
Scripted evidence: .runs/evals/environment/20261013T102019Z-development-scripted.
