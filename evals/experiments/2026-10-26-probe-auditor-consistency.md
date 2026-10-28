# Java probe attribution and Node/Java auditor consistency

## Status and scope

Completed bounded investigation on the physical macOS arm64 host, on the local uncommitted `manus/just` working tree based on `6beebbcb6b3791ec4d5b144bebe245f3c73a23c5`. This is a candidate diagnostic record, not a promoted baseline or population-accuracy result. [ISSUE-0014](../../docs/plans/active/ISSUE-0014-node-java-assessment-live-quality.md) remains open. No commit, push, release, policy relaxation or oracle change was performed.

## Java error attribution

The historical live producer supplied `../fixtures/private/secret.txt` for the operator-fixed root `/fixtures/allowed`. That addresses `/fixtures/fixtures/private/secret.txt`, not the declared `/fixtures/private/secret.txt`. The sibling-relative value is `../private/secret.txt`.

The saved native receipt contained a JUnit failure and trusted `EXECUTION_FAILURE` from an unallowed I/O exception, with no admitted target-execution/coverage claim and confirmed cleanup. It correctly remained `ERROR`; neither a successful guard test nor negative clearance was warranted. No trusted observer or exception rule needed to be weakened.

The new [Docker regression](../../tests/integration/test_probe_paths.py) submits both exact data values through the production evidence path. The malformed value remains `ERROR`; the corrected value produces a validated disclosure with target execution, finding-line coverage and cleanup. Reconciliation returns the same immutable receipt. The focused two-case native run passed, and both cases also passed in the final full suite. Target code never ran on the host.

The producer's existing source-grounding procedure now requires lexical path composition against the actual public packet, shows why a redundant directory is wrong, and distinguishes a correct destination from a proved guard bypass. It adds no tool, script, permission, oracle or custom agent loop.

## Auditor change

The existing system instruction and semantic-review procedure now share one precedence:

1. Use `INSUFFICIENT_CONTEXT` only for a necessary missing or ambiguous source/ABI/fixed-argument/submission link—not unavailable execution evidence, private contents, coverage or broader application context.
2. Reject a materially false, unrelated or source-contradicted claimed mechanism or bypass; do not repair it.
3. Otherwise accept a coherent proposed test, including one honestly expecting a visible guard to hold. Acceptance does not create evidence or establish a completed assessment.

The canonical `AuditResult` remains the native ADK `output_schema`. New scripted native-ADK regressions verify first-request guidance ordering, procedure preload, canonical schema identity, the unchanged outcome-blind packet and the loader-only tool surface. These tests establish delivery and capability boundaries, not model compliance.

## Frozen isolated auditor comparison

Same reviewed provider/settings and unchanged four Node/Java inputs and external oracles, five repeats per case. The pre-change guidance was recovered from a saved wheel extraction; revised guidance has its own resource identity. One provider failure remains in the baseline denominator.

| Case | Baseline decisions | Revised decisions |
| --- | --- | --- |
| node01 | ACCEPT 5 | ACCEPT 5 |
| node02 | ACCEPT 2; INSUFFICIENT_CONTEXT 2; provider failure/no review 1 | ACCEPT 5 |
| java01 | ACCEPT 5 | ACCEPT 5 |
| java02 | ACCEPT 3; REJECT 1; INSUFFICIENT_CONTEXT 1 | ACCEPT 5 |
| Total expected decisions | **15/20** | **20/20** |

All four candidate oracles expect `ACCEPT`. Within-case pairwise decision agreement, counting a missing review explicitly as its own category, rose from 25/40 pairs to 40/40 pairs. This is a descriptive small-cohort consistency measurement, not a significance test or an estimate of vulnerability accuracy. The baseline's operational failure and the different resource identities are not hidden.

The preserved four-case Python safety cohort was run separately, three repeats per case: **12/12** expected decisions, zero operational failures. audit01/audit03 remained ACCEPT 3/3 each; audit02/audit04 remained REJECT 3/3 each. Thus the reviewed false-claim cases did not become automatic acceptance in this run. This small cohort does not establish general false-acceptance resistance.

## Producer diagnostic: remaining limitation

The earlier generic path-guidance diagnostic scored **2/12** exact payload matches; java01 addressed the declared fixture in 1/3 proposals. After the concrete public-layout example, a separately identified five-repeat diagnostic scored **5/20** exact matches, with two explicit provider failures. java01 addressed the declared fixture in only **2/5** proposals. The final full denominator contains five exact matches, six control mismatches, five candidate-exact mismatches, two no-valid-output rows and two operational failures.

These repeats have different sizes and guidance identities; they do not demonstrate a reliable producer improvement. Exact payload matching is not semantic-equivalence or exploit-accuracy scoring. No candidate list, oracle, control requirement or fixture was edited to inflate the result. The path error is diagnosed and regression-covered, but not reliably prevented by the model guidance.

## Distinct composed live repeat

After isolated diagnostics, one fresh four-case batch used the current production ADK factories, real ordinary Temporal activities/workflows, reviewed offline Docker observers, immutable artifacts, normal policy and the official CLI external scorer. The service lifetime was managed by the native Temporal SDK; the batch and artifact identities were new. The frozen two-round guarded-case protocol was unchanged.

| Case | Completed assessment | Native rounds | Evidence/audit |
| --- | --- | --- | --- |
| node01 | DEMONSTRATED | 1 | Healthy control, executed disclosure, ACCEPT |
| node02 | NOT_DEMONSTRATED | 2 distinct admitted adversarial payloads | Healthy controls, executed held attempts, ACCEPT in both rounds |
| java01 | DEMONSTRATED | 1 | Healthy control, executed disclosure, ACCEPT |
| java02 | NOT_DEMONSTRATED | 2 distinct admitted adversarial payloads | Healthy controls, executed held attempts, ACCEPT in both rounds |

The scorer accepted **4/4** completed assessments, with zero incomplete assessments, invalid-positive evidence, forbidden labels, operational failures or unavailable results. Saved result references were independently reconciled and re-scored; all four retained valid evidence/coverage and confirmed cleanup. The report also retains two legacy `disposition=INCONCLUSIVE` rows for the completed guarded assessments; those legacy dispositions are not missing version-2 assessment outcomes.

This is the first successful four-case live repeat at this resource identity, not proof of majority completion across repeated or held-out tasks. Historical 0/4 and 1/4 batches remain preserved. In particular, the weak independent producer diagnostic prevents closing ISSUE-0014. `NOT_DEMONSTRATED` is limited to the admitted finite protocol, not non-exploitability, application-wide clearance or patch verification.

## Usage and identity

| Cohort | Model calls | Input tokens | Output tokens | Cost |
| --- | --- | --- | --- | --- |
| Baseline auditor | 20 | 44,090 | 5,669 | Unknown |
| Revised auditor | 20 | 48,250 | 3,529 | Unknown |
| Preserved Python auditor safety | 12 | 27,978 | 1,624 | Unknown |
| Earlier producer guidance | 12 | 28,734 | 5,144 | Unknown |
| Final producer guidance | 20 | 48,190 | 15,100 | Unknown |
| Composed live batch | 12 | 32,737 | 4,919 | Unknown |

No model-requested tools were used in these runs. Guidance was preloaded; that is not reported as a successful tool call. Missing cost remains unknown.

Final isolated role resource identities:

- Producer: `83c6df6770094ae4d4ff3aa790ba859cdac25e7713cb5b4ce7666a339674ee67`.
- Auditor: `da3221780152da734ebb983110871cd4968d42d52da7ccff0d61231096e348f1`.

Reviewed immutable observer image IDs:

- Python: `sha256:ec868e12ff819c542ebdca87ef0e4550e1da24dabff054f1fa8b2142787be258`.
- Node: `sha256:d316017da6a73280429226c9bda9bd67ce9c968c2b1da2217b82d6190c35fb8f`.
- Java: `sha256:571e606602e0dc2188c9106b3cb58f62c2fb9fd2a87aaef487855dada6baf4e5`.

The complete private reports retain dataset, configuration, model, resource, source, recipe, budget and image identities. All **64** public fixture/dataset files in the pre-task identity index remained unchanged. No endpoint, credential, raw provider response, model reasoning, private fixture content or raw evidence is included here.

## Native qualification, tooling failures and packaging

`nix develop --no-update-lock-file --command just sync check` passed pinned Ruff lint/format, Just formatting, pinned ty with warnings failing, and local documentation checks.

After updating the public records and archiving the bounded plan, `just check` passed again using the installed local tools and pinned root-environment Ruff/ty. `git diff --check` also passed. The final runtime resource identities still matched the independently evaluated identities.

The first final native sweep incorrectly omitted explicit image selectors: **273 passed, 16 failed, zero skips**. Fifteen failures concerned unavailable default Node/Java image tags; the long-probe test also used the wrong/default Python image. This was a test invocation failure, not a reason to retag or mutate images. Its XML/logs remain retained.

The corrected command was `nix develop --no-update-lock-file --command just -- test-all -q -W error`, with VM-shared `TMPDIR`, `CORSAIR_TEST_NODE=1`, `CORSAIR_TEST_JAVA=1`, `CORSAIR_TEST_LONG_PROBE=1`, explicit `CORSAIR_TEST_IMAGE`, `CORSAIR_TEST_NODE_IMAGE`, `CORSAIR_TEST_JAVA_IMAGE` set to the immutable IDs above, and the existing reviewed `CORSAIR_LIVE_CONFIG`. It passed **289 tests, zero skips, zero reported warnings, in 383.37s**. It includes real Docker, genuine SDK-managed Temporal/replay, CLI and rescore subprocesses, installed-wheel checks, scripted native ADK and live-auditor smoke. These boundaries remain distinct.

Terminal-session loss notifications were reconciled from completed report/XML files before deciding whether work needed repeating; completed inference was not resubmitted. A later Nix build invocation was blocked at the local daemon socket and a network permission request was denied. An offline local `uv build --offline`, without either permission, built the wheel and source distribution. The build emitted the existing project-local-cache and build-backend-version-range warnings; archive inspection verified private exclusions despite the cache warning. All **76** runtime source/resource files exactly matched the wheel, and final guidance/canonical contract identities loaded outside the checkout. The native suite separately passed its installed-wheel test. No hermetic or bit-identical cross-platform build is claimed.

The task-owned composed worker/server stopped through the SDK context; its loopback listener closed. The task database was backed up through SQLite's backup API and verified with `PRAGMA integrity_check`. Private state, claims, artifacts and diagnostics remain retained, not pruned.

Current-working-tree Linux amd64 execution and remote CI remain **unrun**. No generic hostile-source observation integrity, exactly-once execution, artifact-host-loss continuation, broad framework/build support or production-readiness claim is made.
