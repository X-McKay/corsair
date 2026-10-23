# Validation record

This implementation starts from `feature/duo-refactor` at `827386b5deed6bbd82d0adad4d45c5ed1c5715a3` and is developed on `feature/differential-oracle-spec-0090`. The review is aligned with the contract/evidence guidance in `X-McKay/playbooks`; it is not a certification, deployment, or merge approval.

## Confirmed checks

The expanded offline suite passed **165 tests**, including real native-runtime parser smoke checks when their SDKs were installed. The original source-tree identity algorithm is preserved. New checks cover full requested-line reachability, malformed and duplicate JSON, exact native path binding, multi-file LCOV isolation, driver/exit-status consistency, build-time source substitution, root-owned support files, reserved-path collisions, bounded agent budgets, proposal-only seeding, checkpoints, and an unavailable auditor.

The final combined command, `pytest -m 'not live'`, passed **186 tests**, including **21 real Docker integration/security checks**, with no skips or failures in the fully provisioned validation environment.

One representative synthetic case for each of Python, Java, JavaScript, TypeScript, Perl, Ruby and C++ passed through the hardened production Docker kernel: clean build, vulnerable control/exploit, and fixed control/exploit. These seven smoke results are confirmed, not substitutes for the full 385-case run.

A wheel and source distribution built successfully. The wheel was installed in a clean virtual environment and imported from outside the checkout; CLI help, seven packaged runtime rows and operator skill resources were present. Upstream Ruff checks for undefined/unused names and invalid escapes passed, and `git diff --check` passed.

## Full-corpus execution

The final generator creates **55 twin cases per language**, **385 case directories**, and **770 source revision variants**. The full hardened Docker run is in progress at the time of this implementation commit. Its eventual result must replace this status before final delivery. Each completed case is saved atomically as `results/NNNN.json`, alongside the native artifact store, so an interrupted aggregate does not erase completed evidence.

The 11 mechanism families and five input variants are synthetic policy regressions. Maven/Gradle, npm/TypeScript/Vite, Python packaging, Bundler/Rake, Perl MakeMaker/prove and CMake/Make execute real build commands. No model or blind auditor is used for trusted-reference benchmark replay. The result measures runtime, build and gate mechanics, not real-CVE exploitation, semantic certification, or LLM accuracy.

## Independent hardening review

A separate static review found and prompted fixes for writable collector support, helper-file substitution during build replay, and reserved support-path redirection. All original entry types, executable modes, link targets and content hashes are checked before sealing, while new build outputs remain allowed. Support files are injected root-owned/read-only; probes use a different non-root uid, no capabilities, and no network. Native collectors execute immutable support code without extra container privileges. Native raw reports are not cryptographic attestations; hostile model-authored build and probe code still needs review.

## Blocked or unrun work

The live GPT-6.1 Sol pilot returned the provider's `cyber_policy` rejection before any submission. It correctly recorded `ERROR` and confirmed workspace cleanup; that refusal was not bypassed. Consequently **no live producer/auditor accuracy result is claimed**, and there is no completed model-accuracy sweep across the corpus. SDK agent-contract tests use controlled models.

The external catalog has **1,032 candidate records** with provenance and license/reuse notes. They are **unexecuted leads**, not imported or validated Corsair fixtures. Some records are ecosystem or project-only candidates rather than confirmed vulnerabilities; TypeScript's inventory explicitly includes JavaScript/TypeScript ecosystem entries whose individual language remains unverified. Production OpenShell, arbitrary framework layouts, and arbitrary compiler/runtime versions are not delivered or certified.

## Reproduction

```bash
make sync
make test-offline
make images
uv run --locked pytest -m 'not live' -q
make benchmark WORKERS=2
```

The sandbox validation uses Docker 29.1.3, network-disabled unprivileged probe containers, the committed toolchain Dockerfiles, and the pinned Python development environment. Images are cached by resolved base-image identity, runtime configuration, source hash and exact build script; altered source or unresolved image identity cannot reuse a stale build. The final report and cleanup confirmation belong to the completed validation record, not this provisional section.
