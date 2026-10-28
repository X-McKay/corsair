# HANDOFF-0150: Scoped outcomes and concrete Node/Java observers

## State

Implemented locally on `manus/just`, based on `6beebbcb6b3791ec4d5b144bebe245f3c73a23c5`. This evolution is not committed, pushed, released or remotely CI-qualified. Previous branch history, stashes, other worktrees and unrelated services were preserved.

[PLAN-0127](../plans/PLAN-0127-outcomes-node-java.md) records decisions and failures. [Qualification](../../../../evals/baselines/qualifications/qualification-outcomes-node-java-2026-10-25.json) preserves exact cohort boundaries and image/instruction/configuration identities. [ISSUE-0014](../../active/ISSUE-0014-node-java-assessment-live-quality.md) remains open for model-driven completion quality.

## Implemented boundary

- Canonical Pydantic recipe variants for existing Python, dependency-free Node `.mjs` named exports with an inserted JSON payload, and one Java public static `String` method with `String` arguments. Settings select their concrete images; manifest identity includes the canonical recipe schema. The recipe and all fixed arguments remain operator-owned.
- Native Node `node:test` JUnit/LCOV reporting and pinned Java JDK/JUnit Platform/JaCoCo/Jackson tooling. Java compilation disables annotation processing. No target build script, model-authored assertion, target dependency installation or target execution runs on the host.
- Versioned `corsair.result/2` paired assessments: `DEMONSTRATED`, `NOT_DEMONSTRATED`, or no completed assessment. Healthy control, admitted native evidence/coverage, confirmed cleanup and accepted outcome-blind audit are mandatory. Negative results require the entire admitted diverse finite protocol; held first attempts do not terminate it. Abstention, repeated candidates, missing evidence, rejected audit and execution/provider errors never become negative clearance.
- Mechanical outcome-blind follow-up, existing immutable operation identities and final-result commits, versioned assessment oracles and exact saved-result scoring. The CLI restores known committed-result references before eval/rescore validation. No second execution ledger or generic runtime registry was introduced.
- Legacy frozen inputs/oracles and result/1 wire behavior remain preserved. Two genuine base-revision, marker-absent Temporal histories are retained and replayed. Role-local native ADK schemas/resources remain authoritative; auditor instructions no longer incorrectly say Python only.
- Aggregate `just images` builds all three trusted observers. Linux native CI explicitly opts into Node/Java tests. Current guides describe actual ABIs, image settings, baseline-only doctor scope, labels, evidence and operational limits.

## Actual qualification

`nix develop --no-update-lock-file --command just check` passed pinned Ruff lint/format, Just formatting, pinned ty with warning failure and maintained local documentation checks. The final documentation-only closure is checked again before delivery.

On the physical macOS arm64 host with the existing Colima Linux VM, full suite `just -- test-all -q -W error` passed **285 tests, zero skips** before final auditor instruction cleanup (369.49s) and again afterward (**376.79s**). Explicit reviewed configuration selected unique image tags, VM-shared `TMPDIR`, `CORSAIR_TEST_NODE=1`, `CORSAIR_TEST_JAVA=1`, their image selectors, `CORSAIR_TEST_LONG_PROBE=1` and the reviewed live-auditor settings. This included real Docker, genuine SDK-managed Temporal, actual CLI subprocesses, native scripted ADK, live-auditor smoke, and installed-wheel coverage. Native doubles remain labelled doubles, not live agents.

The four-case assessment batch and rescore consumer test passed **4/4** using scripted ADK and real Docker/Temporal. It demonstrates both completed outcomes through real evidence and the immutable scorer, not population model accuracy.

Final isolated producer diagnostics: **2/9** preserved Python exact matches and **1/12** new language exact matches. Final language-neutral auditor: **8/12** preserved Python and **8/12** new language cases. Earlier 11/12 and 8/12 auditor-stage reports remain retained. Candidate exact-match mismatch is not a semantic-equivalence or exploit-accuracy result.

The initial full-live four-case cohort resolved **0/4** assessments without operational failures. The distinct final corrected-instruction cohort resolved **1/4**: one accepted Node `DEMONSTRATED`, three incomplete, including one Java trusted-probe execution error. Control construction, audit sufficiency and genuinely diverse grounded follow-up remain quality limits. All cases and denominators remain retained. No `NOT_DEMONSTRATED` was fabricated. Cost remains unknown.

## Packaging and preservation

Fresh wheel and source distribution built. The wheel's complete runtime source/resource bytes matched the final source identity; native role resources and Node/Java driver resources loaded outside the checkout. Package inspection excluded private/generated state. `uv build` emitted its project-local cache and build-backend version-range warnings; both are retained and do not imply hermeticity. All **37** original frozen input/pin identities remained unchanged; new candidate cohorts are separate and unpromoted.

Task-owned live worker and Temporal service were stopped; the loopback listener is closed. The task SQLite database was backed up and checked with SQLite integrity verification, not moved blindly. The managed-container listing was empty. The original Python image tag is unchanged; uniquely tagged reviewed images and all private evidence/state remain retained. A process-list inspection was permission-blocked; cleanup assertions rely on the exact service lifecycle, closed listener and container checks, not a claimed complete host process inventory.

## Not qualified / next work

Current-revision Linux amd64 execution and remote CI are **unrun**. Do not reuse older CI as proof for this working tree. The newly configured CI gates require publication to execute.

No claim is made for broad npm/framework/TypeScript or Maven/Gradle builds, arbitrary code probes, hostile-interpreter/JVM observation authenticity, application-wide non-exploitability, broad patch verification, artifact-host-loss continuation or production readiness. Candidate datasets need human review; there is no baseline promotion.

The next bounded improvement is ISSUE-0014: improve source-grounded controls/probes and independent semantic review, then repeat frozen role and composed evaluations with a new identity. Discuss the recipe-specific diverse protocol where no second grounded candidate exists; do not silently weaken its negative-evidence definition merely to increase completion. Publish only with the user's current authorization.
