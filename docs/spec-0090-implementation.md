# SPEC-0090 implementation contract

This branch starts at `827386b5deed6bbd82d0adad4d45c5ed1c5715a3` on `feature/duo-refactor`. The attached SPEC-0090 is the design input. The existing branch already owns a single producer, a deterministic kernel, a stateless auditor, clean build snapshots, and separate offline twin probes. Extend these rather than add a competing architecture or duplicate model schemas.

## Boundaries

The requester and repository owner is X-McKay. This implementation is a review candidate, not a certification or deployment. Inputs are reported findings and immutable source revisions. Operator configuration owns runtimes, model endpoints, credentials, budgets, and skills. Findings and repository text are untrusted data. Evaluator oracles must never enter the producer context. All generated probe and build code runs inside hardened Docker containers; the host only reads source, collects artifacts, and controls Docker.

One Python module declares `CONTROL_PAYLOAD`, `EXPLOIT_PAYLOAD`, and exactly one synchronous `run_target(payload)` function. The same function calls the real target, including subprocesses for other languages, and checks the same security invariant. Its native target runtime is selected from the operator matrix, never from model-produced policy. Coverage comes from coverage.py, c8/V8 with source maps, JaCoCo, SimpleCov, Devel::Cover, or gcov, not a fabricated target marker. Coverage must identify the exact target and all requested vulnerable-revision lines in both probes. An application exception, unrelated crash, missing instrumentation, timeout, or ambiguous report is not proof.

Keep the existing K1/K4 labels and fixed-revision annotation semantics, which are more cautious than the draft's `REFUTED` label. One negative input cannot prove absence. Keep one outcome-blind audit after deterministic gates; it can only reject. Verification without a model auditor remains an explicitly reported deterministic-only mode for reproducible kernel testing, not semantic certification.

## Execution and stopping

The producer has only `bash`, `read_skill`, and `submit`. Existing finite submission, shell, request, token, and command-time budgets remain operator-owned. Reject malformed limits before creating resources. Record progressive submission checkpoints and tool observations, including timing, errors and bounded size/mtime file-change metadata, without serializing credentials or hidden reasoning. A checkpoint is an observation, not permission to rerun uncertain effects automatically.

Seeding and skill crystallization are bounded optional proposal operations using PydanticAI. They return structured artifacts, never silently mutate the user's tree or operator skills. Candidate patches require operator review and testing; a successful synthetic fixture is not evidence for a real vulnerability or model quality.

## Acceptance criteria

- AC01: Existing offline regression suite passes; original Python fixture still verifies and its fix is checked in real offline twin containers.
- AC02: Guard rejects nested/duplicate/rebound driver symbols, invalid arity, mocking aliases, payload-identity branches and constant assertions before any build or audit.
- AC03: Both vulnerable-revision probes cover every requested target line. Exact path binding rejects basename collisions, traversal and ambiguous native reports. Missing evidence fails closed.
- AC03a: Original source entries, including helpers, directory types and symlink targets, remain unchanged through build replay. Sealed source and kernel support files are root-owned/read-only to the distinct, non-root probe uid. Source collisions at the reserved `.corsair` path and build-time support-path redirection fail before probes run.
- AC04: Python, Java, JavaScript, TypeScript, Perl, Ruby and C++ execute real targets through one probe contract. Standard Maven/Gradle, npm/Vite/TypeScript, Python packaging, Ruby Bundler/Rake, Perl MakeMaker and CMake/Make builds are represented or limitations are explicit.
- AC05: At least 50 reproducible synthetic twin cases per language have stable IDs, paired vulnerable/safe revisions and documented mechanism/payload variants. The delivered generator has 55 per language, satisfying the user's 50-plus request; these are variants of 11 policy families, not 55 unique vulnerabilities. Real external candidates are separately catalogued with sources and never counted as executed examples.
- AC06: Benchmark reporting includes expected/observed outcome, all gate failures, native instrumentation and framework, durations and source identity; unavailable runtimes are blocked, not passed. Hard invariant failures make the runner nonzero.
- AC07: Seed and optimizer output are schema-validated proposals only, with tests for missing dependencies, invalid paths and malformed output. Skills are reviewed Markdown, policy remains deterministic Python.
- AC08: Run implementation tests end-to-end, perform final cleanup, rerun the complete relevant suite, then package the committed source. Report passed, failed, blocked and unrun checks distinctly.

## Playbooks alignment

Use the Python local coding profile and the specify-agent-contract/build-agent-evals development guidance in `X-McKay/playbooks` at `2b31000fbc8c9a788448b049d25809927c4d91f9`. Preserve their separation between proposal, enforcement, execution, evidence and release decisions. This document maps CONTRACT/ANATOMY/PROMPT concerns to AC01–AC08; it does not claim approval under that playbook. Use standard-library composition and the existing PydanticAI, pytest, coverage and Docker boundaries. No scheduler, workflow engine, service framework or custom tracing infrastructure is needed in Corsair.

The draft's automatic patching and automatic skill application are deliberately proposal-only here: neither a model nor a successful trace may silently change source or operator guidance. Its `REFUTED` wording is replaced by the existing more cautious K4 semantics, and its per-language drivers share one Python driver with native SDK coverage rather than duplicating the entire execution loop seven times. Production OpenShell integration remains outside this Docker-backed review branch. These are explicit implementation choices, not hidden omissions.
