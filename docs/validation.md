# Validation record

This is the preserved pre-refactor implementation record. See the [agent-package architecture record](architecture-refactor.md#validation) for the current layout, post-cleanup tests and subsequent CI validation.

The implementation branch is **`feature/differential-oracle-spec-0090`**, cut from `feature/duo-refactor` at `827386b5deed6bbd82d0adad4d45c5ed1c5715a3`. Implementation and fixture fixes are at `ee5f3661694bffc914e960393695a37ea1f339a5`; the following evidence-only commit adds this completed record. The work follows the contract/evidence separation in `X-McKay/playbooks`, not a certification, deployment or merge approval.

## Final results

| Check | Result |
| --- | --- |
| Final post-cleanup test suite, `pytest -m 'not live'` | **188 passed**, including **21 real Docker checks**, no skips or failures |
| Final retained kernel benchmark cases | **385 passed: 55 per language** |
| Source revision variants / final retained probe runs | **770 revisions / 1,540 probe runs** |
| Final GitHub workflow | **Success: contracts and all seven language shards** |
| Static correctness checks | Ruff `F,W605` and `git diff --check` passed |
| Packaging | Wheel and source distribution build; installed-wheel CLI/resources verified outside checkout |
| Final container cleanup | No Corsair-labelled containers remaining; no unconfirmed removals |

The successful GitHub run is [39894115044](https://github.com/X-McKay/corsair/actions/runs/39894115044), on the final implementation commit. It independently builds fresh images and replays all 55 cases for each language. Its artifact-retention action emitted a non-failing Node runtime deprecation annotation; every job completed successfully.

[Machine-readable benchmark evidence](benchmark-results.json) records each case's vulnerable/fixed source identities, submission digest, runtime row, timing, observed role outcomes, target-line coverage and confirmed cleanup. This is **trusted-reference kernel validation without model calls**, not a model-accuracy or semantic-certification result.

## Exhaustive run and repairs

The first complete local 385-case run passed 315 cases and rejected 70. Strict TypeScript detected 50 fixture literal-narrowing errors; Perl coverage rejected 20 fixture target-line bindings affected by physical control characters in generated source. Neither failure was converted into a pass, and no kernel gate was weakened.

After fixing generated TypeScript typing and Perl escape literals, **all 55 TypeScript and all 55 Perl twin cases were rerun through the production Docker kernel and passed**. The final local record retains the other five complete passing language suites and replaces the two affected suites with their complete reruns. Every retained source and submission digest was then compared against the final generator output. The final fresh GitHub run replayed all seven complete language suites successfully. The original failed run remains visible as [39891996047](https://github.com/X-McKay/corsair/actions/runs/39891996047); the evidence does not conceal it.

## Languages and frameworks actually exercised

| Language | Final twin cases | Native evidence / build systems |
| --- | ---: | --- |
| Python | 55 | coverage.py; pip/setuptools packaging |
| Java | 55 | JaCoCo; Maven and Gradle |
| JavaScript | 55 | V8/c8 LCOV; Node/npm |
| TypeScript | 55 | c8 remapped source lines; strict TypeScript and Vite |
| Perl | 55 | Devel::Cover; MakeMaker/Make/prove |
| Ruby | 55 | SimpleCov; Bundler/Rake |
| C++ | 55 | gcov JSON; CMake and Make |

The cases span **11 mechanism families and five input variants**, with paired vulnerable and fixed source revisions. They execute real compilers, build tools, native targets and coverage SDKs, but their security behavior is synthetic policy computation. They are **not 385 unique vulnerabilities, production-framework exploit chains, or reproduced CVEs**. The full framework/version space is not certified.

## Independent hardening review

A separate static review identified writable collector support, helper-file substitution during build replay, and reserved support-path redirection. Fixes preserve all original entry types, executable modes, link targets and content hashes before sealing, while allowing newly generated build outputs. Source collisions at `.corsair` and build-time support-directory redirection are refused. Support files are injected root-owned/read-only, and probes run as a distinct non-root uid without network or capabilities. Native collectors execute immutable support code without extra container privileges.

The final regression suite checks full requested-line reachability, exact path binding, malformed/duplicate JSON, multi-file LCOV isolation, driver/native/exit-status consistency, direct and helper-source substitution, immutable support files, reserved-path collisions, budget validation, atomic checkpoints, proposal-only seeding, and unavailable auditors. Raw native reports are **not cryptographic execution attestations**. Hostile model-authored builds and probes still require review; containers are not a guarantee against escapes.

## Blocked or unrun work

The live GPT-6.1 Sol pilot returned the provider's `cyber_policy` refusal before any submission. Corsair recorded `ERROR` and confirmed workspace cleanup; the refusal was not bypassed. **No live producer/auditor accuracy claim or live model sweep is made.** Agent contracts and proposal handling were tested with controlled SDK models.

The research catalog contains **1,032 external candidate records** with source and license/reuse notes. They are **unexecuted leads**, not imported or validated Corsair fixtures. Some are ecosystem/project-only candidates rather than established vulnerabilities; TypeScript's catalog explicitly includes JavaScript/TypeScript ecosystem entries whose individual source language remains unverified. Upstream source, license, exact revision pairs, bounded triggers and oracles must be checked before promotion to executed benchmarks.

Automatic patch/skill application is deliberately proposal-only. Production OpenShell integration, arbitrary framework layouts, and arbitrary compiler/runtime versions are not delivered. Builds that deliberately rewrite original tracked source fail closed until an operator explicitly designs a suitable policy.

## Reproduction and delivery workflow

```bash
make sync
make test-offline
make images
uv run --locked pytest -m 'not live' -q
make benchmark WORKERS=2
```

Validation used Docker **29.1.3**, the committed Debian-based runtime Dockerfiles, offline unprivileged probes, and the pinned development environment. Resolved runtime image identities are recorded in the JSON evidence. Source/image/configuration/build-script cache keys prevent stale replay. The completed workflow was implementation, end-to-end testing, final static/documentation cleanup, post-cleanup retesting, evidence verification, confirmed container cleanup, and packaging of the final committed source.
