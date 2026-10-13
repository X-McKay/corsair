---
id: HANDOFF-0120
kind: handoff
title: Unit tests at application seams
status: recorded
updated: 2026-10-13
related: [SPEC-0075, PLAN-0090]
---

# Unit tests at application seams

## Verified state

Base is detached HEAD 1815f75498c0acbbd35dcaa20a42cef737e76866. Implementation remains uncommitted in the shared worktree. Earlier HANDOFF-0118/0119 review files and their CURRENT pointer were preserved. No PR publication, merges, provider calls or deployments occurred.

User authorized implementation across all languages, frameworks and CWEs and parallel Sol 6.1 work. Three agents handled planning, authoring/native fixture and documentation/assessment while root implemented the shared gates and composition. Existing five roles suffice: assessment independently reviews test validity after authoring; no new agent or recorder framework was added.

Delivered:

- Planner declares typed return-value, exception, fixture-state or dependency-call observations at existing application seams. Dependency calls describe their controlled double. Both tests use one consistent mode. Legacy effect-witness plans remain supported.
- Authoring allows native recording doubles and application-owned dependency references in unit mode. Source/interpreter integrity constraints remain. Semantic review establishes whether a replaced object is a dependency and whether the real property remains under test; syntax does not establish that fact.
- Assessment reads the reported condition, full plan, frozen patch and exact per-revision source. Its four validity conclusions are source linkage, condition exercised, assertion relevance and dependency scope. Trusted code attaches citations and binds the retained review to source and observation-plan/patch digests. These are independent model judgments, not formal proof or runtime attestation.
- Unit gates need no low-level recorder. They require valid review and native execution; absent/negative/stale review, wrong identities, failed control, unplanned assertions, skips, operational failures and interference cannot establish safety. Optional contradictory witnesses still block conclusions.
- Composition publishes bounded captured source snapshots, checks their revision identity, and uses the final assessment gate. The verdict progress event occurs after assessment. Native direct and durable paths share routing and contracts; durable request JSON roundtrip covers new snapshot fields.
- Legacy evidence defaults serialize without changing frozen evaluation bytes. Historical assessment output can deserialize with absent new fields; this is not a claim of live old-history replay qualification.
- Authoritative docs, AGENTS and shared development/review/scaffold/base-image skills now preserve the property-driven approach. Native SQL fixture demonstrates query construction without a database, with exactly two finding tests. It is an example, not a SQL/CWE-specific production branch.

## Validation and blockers

Full offline command (same test selection as make test-config), using the isolated locked review environment:

```sh
PYTHONPATH=src:. env -u NO_COLOR TERM=xterm /tmp/corsair-pr-review/venv/bin/python -m pytest -q -n 4 tests/configuration tests/unit tests/agents tests/temporal/test_fixture_contracts.py tests/temporal/test_issue_analysis_composition.py tests/temporal/test_chain_composition.py
```

- Initial full run: 2004 passed, 5 failed, 1 skipped. Three failures were newly serialized defaults changing frozen evidence/manifest bytes; fixed with native Pydantic default exclusion without modifying frozen cases. One was a historical toolset hash intentionally changed by new tool guidance; updated the expectation explicitly. One terminal test inherited TERM=dumb/NO_COLOR from this host; rerun with a terminal-test environment. Log `/tmp/corsair-unit-full-tests.log`.
- Second full run: 2016 passed, 1 failed, 1 skipped. Remaining failure expected the gate progress event before assessment. New validity review requires the final event after assessment; updated the event assertion. Log `/tmp/corsair-unit-full-final.log`.
- Final affected run: 63 passed (run activity, unit composition, evidence assessment). Log `/tmp/corsair-unit-final-focused.log`. The complete suite was not repeated after this event-order correction.
- Native reviewed SQL fixture: unsafe concatenation control passes/security fails; parameterized source both pass, no database. Included in authoring checks/full suite.
- Source binding and builder checks: 41 passed; final unit composition/durable serialization set 4 passed. Logs `/tmp/corsair-unit-sourcebinding-tests.log`, `/tmp/corsair-unit-sourcebinding-final.log`.
- Frozen isolated scripted comparisons: planning 12/12 before and after; authoring 20/20 before and after; assessment 54/54 before and after, no evaluator failures. These demonstrate contract/evaluator behavior, not live model correctness. Evidence: `/tmp/corsair-unit-planning-before`, `/tmp/corsair-unit-planning-after-final`, `/tmp/authoring-unit-before-host`, `/tmp/authoring-unit-final-host`, `/tmp/corsair-unit-assessment-before`, `/tmp/corsair-unit-assessment-final-source-guidance`.
- Initial restricted-socket planner/authoring runs stalled and were interrupted with exit130; host loopback-enabled retries passed. One agent attempted a nonexistent tests/core/test_disposition.py selection (exit4); corrected selections passed. An initial assessment test incorrectly required the short gate-plan citation despite the full plan being cited; corrected to require full plan and reported condition.
- Retained skip and inherited multiprocessing/event-loop deprecation warnings do not represent new qualification.

Live provider semantic review calibration, broader native language/framework/CWE fixtures, Docker/OpenShell composition and historical Temporal replay are unrun at this source. No blanket support or accuracy gain is claimed. Missing source visibility remains a validity limitation; external engine/deployment/concurrency behavior requires evidence at that scope.

## Decisions and next steps

Maintain one property/observation contract and one deterministic gate across languages and CWEs. Do not add per-CWE recorder requirements. Framework adapters own native execution and result parsing; every new supported runtime and semantic property needs appropriate fixture evidence. The SQL example establishes construction, not database-engine behavior.

Next qualification should measure independent assessment on valid and deliberately invalid unit tests (substitute implementation, vacuous assertion, dependency double implementing the safety guard, wrong source, wrong property), through existing per-agent provider configuration. Preserve frozen baselines and separate live judgment quality from scripted plumbing. Keep exactly the two finding-specific tests.

## Continuation prompt

```text
Read AGENTS.md and docs/development/CURRENT.md, SPEC-0075, PLAN-0090 and HANDOFF-0120. Inspect git/source state and preserve unrelated review records. Unit tests at existing application seams are the accepted default across languages/frameworks/CWEs. Use the development/review skills. Verify the shared planner-authoring-assessment-disposition path and the retained offline evidence. Continue with bounded live semantic-review evaluation or an actual supported-runtime unit case using existing provider/runtime configuration; do not reintroduce mandatory low-level witnesses. Missing source or execution evidence remains inconclusive. Update records with actual outcomes and do not claim live or all-language qualification from host checks.
```
