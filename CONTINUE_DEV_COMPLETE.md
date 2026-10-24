# Continue Corsair to development completion

Use this file as the continuation prompt for a fresh development session.

## Mission and authorization

Continue the `implement/multilingual-benchmark` branch until the approved multilingual benchmark, measurement, release-gate, and iterative-improvement work is development complete. Work autonomously, use parallel research/review agents where tasks are independent, commit coherent reviewed checkpoints, and push them to the same branch. Do not stop merely to report partial progress. Ask the user only when an external credential, environment repair, irreversible action, or genuinely product-defining choice cannot be resolved from the approved documents.

The repository owner has already approved this design and implementation direction, including Apache-2.0 for Corsair-authored benchmark material. This does not relicense upstream source or evidence. Do not reopen settled terminology or design decisions unless implementation evidence contradicts them.

Start by fetching and checking out `implement/multilingual-benchmark`, then verify that its remote head contains commit `af63aa8bc0d45e4f9923307bc9a040d2ea171759`. Read `AGENTS.md` before changing anything. Use the applicable repository/playbook skills, the existing worktree or a new isolated worktree, test-driven implementation, independent review after each substantial batch, and verification before claiming completion.

## Approved sources of truth

Read these in order:

1. `AGENTS.md`
2. `docs/superpowers/specs/2026-10-23-multilingual-benchmark-and-improvement-loop-design.md`
3. `docs/superpowers/plans/2026-10-23-probe-verdict-contract.md`
4. `docs/superpowers/plans/2026-10-23-multilingual-script-coverage.md`
5. `docs/superpowers/plans/2026-10-23-corpus-qualification.md`
6. `docs/superpowers/plans/2026-10-23-evaluation-metrics-and-release-gates.md`
7. `docs/superpowers/plans/2026-10-23-azure-remediation-eval-skill.md`

When a plan names an upstream candidate that fails the v2 contract, runtime, rights, determinism, or exact-coverage gate, replace it with an independently licensed candidate while preserving language balance, family independence, and framework/vulnerability diversity. Record the substitution and why the original was rejected.

## Contract that must remain invariant

- The canonical contract is `corsair-lite/differential-probe/2`.
- One probe accepts only a payload and uses the same setup, target call, owned sink, and Boolean invariant for control and exploit roles. It cannot receive role, revision, expected result, label, or oracle information.
- Boolean `true` means the invariant held; Boolean `false` means the reported condition occurred.
- Control `PASS` means `true`. Exploit `PASS` means `false`. Exploit `FAIL` means a clean `true`.
- Source control `PASS` plus exploit `PASS` produces canonical `LIKELY_EXPLOITABLE`.
- Fixed control `PASS` plus exploit `FAIL`, with all decisive gates satisfied, verifies the remediation and supports scoped `LIKELY_NOT_EXPLOITABLE` for that exact finding, payload, revision, and runtime.
- `POTENTIALLY_EXPLOITABLE` is explanatory prose only. Do not add it as a second enum.
- Exceptions, malformed output, missing coverage, missing reports, target mismatch, and infrastructure failure cannot prove a negative. A removed fixed target is `INCONCLUSIVE/TARGET_REMOVED` and `not_verified`.
- Functions, methods, scripts, CLIs, and Java main entry points use the same contract. Child-process output or exit status is insufficient without verified native target coverage.
- Labels and evaluator oracles must never enter agent-visible cases, prompts, skills, or tool output.
- Never run model-written or upstream benchmark behavior on the host. Replay it only in bounded, disposable containers.

## Verified checkpoint at `af63aa8`

The branch already contains:

- The v2 verdict contract and multilingual function/method/script/CLI/Java-main execution support.
- Strict evaluator-only corpus schemas, provenance and rights checks, quarantine boundaries, immutable replay/admission receipts, race/path hardening, revision-specific target-line mapping, vendored source identity, and authored-license scoping.
- Runtime-rights Phase A evidence for frozen Python, JavaScript, Java, and Perl images. Commits `ac0cc1a6`, `2256cf07`, and `2d5624af` passed independent review. Applicability, distribution obligations, independent rights conclusions, and stable clean-rebuild identity remain Phase B blockers.
- Candidate cases through Batch D: `cs-1001` through `cs-1016`, four real upstream families per language, plus four authored conformance families. Batch C is in `b3f31c9a` and `63d66ba1`; Batch D is in `af63aa8`.
- Batch D independently reviewed READY as candidate packaging. Its focused suite had 205 passing tests and corpus validation passed. Final native four-way replay, exact target coverage, full offline tests, receipts, and admission were not claimed because the previous executor was exhausted.
- The scored manifest intentionally contains no unqualified rows. Candidate packaging is not admission, and current qualified/scored count remains zero until rights, runtime, replay, receipt, and independent-review gates all pass.

On a healthy executor, first rerun the blocked Batch D native checks and `make test-offline`. Preserve any honest failure rather than converting it into a positive or negative disposition.

## Immediate Batch E work

Implement `cs-1017` through `cs-1020` only after closing each row's remaining preparation gates:

### `cs-1017` — Flask

- Source: `9532cba45d2339e90ebf04f178b1e4f2064e7328`, the first parent of fixed merge `70f906c51ce49c485f1d355703e9cc3386b1cc2b`.
- Target: `src/flask/sessions.py`, `SecureCookieSessionInterface.save_session`, mapped line `334 -> 338`.
- Prepared closure: 18 unchanged Flask source files plus six pinned wheels.
- Safe invariant: whether `Cookie` is present in an owned in-memory response's `Vary` header. Source measured `true/false`; fixed measured `true/true`, with native target coverage in preparation.
- Preserve the merge topology and exact source/dependency rights evidence. The runtime still needs Phase B closure and final serialized replay.

### `cs-1018` — node-tar

- Source release: `1e33534e1e96ca6385b3a4749876aea2cda61cea`.
- Behavioral fix: `9dbdeb6df8e9dbd96fa9e84341b9d74734be6c20`.
- Fixed release: `3f7b20097e0daba10441507becbf5b87c6b83b8b`.
- Target mapping: `lib/unpack.js` line `468 -> 472`, symbol `Unpack.[CHECKFS2]`.
- Prepared closure: 13 source files and six dependencies. The owned-root four-way result and native coverage were observed during preparation.
- Preserve all three commit identities; the fixed release is not itself the behavioral patch.

### `cs-1019` — Java replacement

The planned zt-zip row is rejected: its fixed path throws a caller-visible `ZipException`, so it cannot establish a clean negative under v2.

Use Apache Commons BeanUtils only if its normal-return design closes cleanly:

- Source: `a83c1eae04c9c99360c3ba4e6a46fd89dc5407ef`.
- Fixed: `62e82ad92cf4818709d6044aaf257b73d42659a4`.
- The verified production diff adds `SuppressPropertiesBeanIntrospector.SUPPRESS_CLASS` to `PropertyUtilsBean.resetBeanIntrospectors()`.
- Exercise `PropertyUtilsBean.describe(ownedBean)` for both roles with one caller-owned map.
- Use the single invariant `!sink.containsKey(payload)`. Control payload is a guaranteed-absent owned sentinel; exploit payload is `class`. Expected source is `true/false`; expected fixed is `true/true`.
- Both roles must use the identical bean and `describe()` path. Validate the benign authored property/value as fixture integrity. Do not catch an exception and turn it into `true`.
- Before packaging, close exact source/tree/blob/patch hashes, minimal unchanged source and dependency closure, Apache-2.0/NOTICE evidence, Java 21 compatibility, four-way container replay, and exact JaCoCo target coverage. If BeanUtils fails, select and document another exception-free Java reserve rather than weakening the contract.

### `cs-1020` — HTTP::Tiny

- Source: `7ac1006118fb9dc00c9c737023b150317622d528`.
- Fixed: `d73c7651e82ace02693842df55928b6c3ae7c38d`.
- Minimal upstream source is `lib/HTTP/Tiny.pm`; preferred common target is line `1397` in both revisions.
- The safe owned sink replaces handle opening only; public `request`, request writing, and header handling remain upstream.
- Invariant: an authored marker header line is absent from the owned sink. Local preparation measured source `true/false` and fixed `true/true`.
- The fixed exploit path's documented HTTP `599 Internal Exception` is a valid normal public result only when the probe itself completes normally, validates the exact response and empty sink, and returns the payload-only Boolean. Uncaught exceptions and unexpected responses remain errors.
- Rerun all four roles in the immutable Perl image and prove exact line-1397 Devel::Cover coverage. Earlier immutable-image evidence covered only both controls at method-entry line 1385.

Reacquire all temporary preparation material by immutable URL and hash. Do not depend on `/tmp` from the earlier executor. Independently review Batch E before pushing it, and keep every row candidate-only until admission gates pass.

## Corpus completion boundary

Development completion requires exactly 44 qualified independent public families:

- Four conformance families, one per language, with direct/script variants sharing family weight.
- Forty real upstream families: exactly ten each for Python, JavaScript, Java, and Perl.
- At least 48 execution variants.
- No backlog, quarantine row, alias, translated synthetic case, private regression, or extra variant may inflate the family count.

Continue through Batches F-J in the corpus plan. Use the exact commit pairs there as candidates and enforce every runtime, rights, provenance, behavior, coverage, replay, and independence gate. Keep package/framework and vulnerability-type strata visible; add independent replacements where needed to preserve breadth. Complete runtime-rights Phase B and stable clean-build image identity, then generate immutable replay/review receipts and admit only passing cases. Run the final inventory assertions, `make corpus-check`, and `make benchmark-verify EVAL_SET=release ATTEMPTS=3` before freezing the content-derived development dataset version.

## Metrics and 80% release gate

After corpus contracts are stable, implement the approved metrics plan without adding a second workflow engine:

- Immutable run manifests and append-only per-attempt records with hashes for provider/model config, producer/auditor prompts, loaded skills, policy, matrix, images, kernel/tools, dataset, oracle/reference revisions, budgets, and sampling settings.
- Acquisition, generation, audit, build, control, exploit, and end-to-end monotonic latency.
- Input, output, cached, and reasoning tokens, preserving unavailable categories as `null`.
- Provider-reported cost or a deterministic estimate tied to an exact versioned pricing-table entry and file hash.
- Controlled model selection and comparison. Reject or prominently mark comparisons whose non-model inputs differ.
- First-attempt family-weighted paired accuracy plus success within three, hard-gate ledger, failure reasons, p50/p95 latency, tokens, and cost in JSON and Markdown.
- Strata by language, vulnerability type/CWE, framework/package, and execution mode with exact numerators and denominators.
- A release fails below 80% overall or below 80% in any of Python, JavaScript, Java, or Perl. Vulnerability-type and framework strata become 80% gates at five independent families; smaller strata remain visible and informational.
- Known-vulnerable `LIKELY_NOT_EXPLOITABLE` and known-fixed `LIKELY_EXPLOITABLE` outcomes are absolute failures that cannot be averaged away.
- Freeze the first live qualified baseline policy before prompt/skill tuning. Scripted providers and sandbox doubles prove mechanics only and never model quality.

## Azure DevOps testing-and-improvement skill

Implement the repository-local developer skill from the approved plan; do not add a public `corsair improve` CLI.

The skill accepts closed/remediated Azure DevOps work-item IDs and read-only workspace configuration. For each issue it must:

1. Resolve the originally attached vulnerable commit from immutable relation/update history.
2. Resolve that issue's actual remediation branch and pin its latest remediation revision; never assume one global remediation branch.
3. Generate one private paired evaluation and run exactly one baseline attempt.
4. Require vulnerable `LIKELY_EXPLOITABLE` and fixed `LIKELY_NOT_EXPLOITABLE`, or one reviewed inconclusive reason such as `TARGET_REMOVED`.
5. Record accuracy, latency, tokens, cost, language, framework, execution mode, and vulnerability type.
6. Register every observed failed case in the private candidate registry before changing prompts, skills, policy, or code.
7. Diagnose and improve without editing oracles, retrying until green, leaking private source into the public corpus, or mutating Azure DevOps.
8. Promote a corrected case into durable private regression coverage, then rerun the related strata and full regression suite.

Allowlist Azure read operations and reject create/update/delete/comment/tag/complete/push verbs before subprocess execution. Keep credentials and authorization headers out of argv, output, stored JSON, errors, and Git.

## Required verification and finish condition

For each coherent change, run the focused tests first, then the repository gates required by `AGENTS.md`. Record every check as passed, failed, blocked, or unrun. Use `make test-offline` for every change, `make test` for kernel/sandbox/image changes, `make eval` for prompt/skill behavior, and live `make pilot` or release evaluation only when approved provider credentials exist. A provider or infrastructure outage is blocked evidence, never a pass.

Before declaring development complete:

- Obtain independent code/data review of the final branch and resolve blocking findings.
- Verify the exact remote head matches the reviewed local commit.
- Confirm all 44 public families are qualified and counted correctly, all final corpus and release checks pass, metrics and model comparison work, the 80% policy is enforced, and the Azure developer skill passes its pressure scenarios and tests.
- Update readiness documentation with exact evidence and remaining operational limitations. Do not claim live model quality, live Azure behavior, legal approval, or release readiness when the necessary credentials or evidence are unavailable; report those items as explicitly blocked while still completing all testable development work.

Keep the implementation simple, organized, and shared across languages and frameworks through the matrix, kernel, adapters, and data rather than language-specific control flow.
