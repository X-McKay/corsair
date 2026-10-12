---
id: HANDOFF-0029
kind: handoff
title: Foundation PR review and merge
status: recorded
updated: 2026-10-12
related: [PLAN-0020, PLAN-0021, ISSUE-0006, ISSUE-0007]
---

# Foundation PR review and merge

## Verified state

The user requested review of all open PRs and merging those ready. Root inventoried all18, checked exact heads, CI and unresolved review threads, and delegated independent Sol reviews of PR2–8 and PR9–16. Root reviewed PR17–18; a Sol reviewer independently assessed PR1 and its upstream patch notes. No blocking findings remained within the documented bounded scopes. There were no unresolved GitHub review threads. Draft status was removed only as reviewed entries were merged, in dependency order with native merge commits; branches were retained.

PR2–18 are merged into main. Final foundation main is `e2ea65888acb49a0839e463176d88db9eeda977e`; its Git tree `26662727c7d711c400fadbf84eec203813e1a8cb` exactly equals reviewed source `a120b6d8474371befea1c4cf3cdfe92b5249256a`. Historical qualification remains bound to the original source and evidence, not newly asserted from merge status.

| PR | Confirmed merge commit |
| --- | --- |
| [#2](https://github.com/X-McKay/corsair/pull/2) | `2b8a816528048502874ed92037f81b9ab3a3e76b` |
| [#3](https://github.com/X-McKay/corsair/pull/3) | `25755709573b2faf214ca115b19dc1497d105824` |
| [#4](https://github.com/X-McKay/corsair/pull/4) | `543078d635d7916569dc73eabf2e78c07aeb1acd` |
| [#5](https://github.com/X-McKay/corsair/pull/5) | `de00f3dc39ae19fd23a4fe6e1f7a3a116271220a` |
| [#6](https://github.com/X-McKay/corsair/pull/6) | `e4ec8d57557a014896691f4d158dc720e0e225d8` |
| [#7](https://github.com/X-McKay/corsair/pull/7) | `4b66e921778fb7ccdc6a29cd48e7620aaa82c58c` |
| [#8](https://github.com/X-McKay/corsair/pull/8) | `19a6ec536ed9abd336d08e07dc8ae679bb89b46c` |
| [#9](https://github.com/X-McKay/corsair/pull/9) | `e21aa5fbfaf1a4a317ccf790551c70dea115bd94` |
| [#10](https://github.com/X-McKay/corsair/pull/10) | `595232c5167a19b383cadbecdc6bf64e55447612` |
| [#11](https://github.com/X-McKay/corsair/pull/11) | `cbfaebcc17c3791643f3ad16cdeeefaf2f6b6277` |
| [#12](https://github.com/X-McKay/corsair/pull/12) | `40bc5072371e6fd708bd3649ab3fa1da0718573a` |
| [#13](https://github.com/X-McKay/corsair/pull/13) | `925a58e6602f203fa51b19a3ba96520f424a1f46` |
| [#14](https://github.com/X-McKay/corsair/pull/14) | `19630e2584f173f4a2fb44b97adb6eb48699ba7d` |
| [#15](https://github.com/X-McKay/corsair/pull/15) | `3c2bb4dfe86381d98ea90ea9e3c5f61e024c3a59` |
| [#16](https://github.com/X-McKay/corsair/pull/16) | `038153b80e1375c44ad0ec762e12f535f19c94b3` |
| [#17](https://github.com/X-McKay/corsair/pull/17) | `307e33bae7d809d86b096d7d433fa23bac5a6044` |
| [#18](https://github.com/X-McKay/corsair/pull/18) | `e2ea65888acb49a0839e463176d88db9eeda977e` |

PR1's old Dependabot branch automatically advanced from `9c545b2ce979558e6d003e6b54c5b3a915d8fd0e` to `86f4879df13ceadf063e588fc4fd323ec3eaf641` during foundation merging. That refreshed patch was reviewed. Main was merged into it without rewriting history; pyproject/lock conflicts were resolved from final main, retaining all dependencies and changing only pytest9.0.2→9.0.3. CI-pinned uv0.12.23 regenerated the lock (format revision3→5). At this document's preparation PR1 awaits publication/exact-head CI and merge. Resolve its final published head and merge via `gh pr view 1 --json state,headRefOid,mergeCommit,statusCheckRollup`; resolve the commit containing this handoff with Git rather than assuming a future SHA.

## Validation and blockers

Private evidence root `.runs/pr-review-20261012/` contains original inventory, exact-head diffs, review summaries, raw qualification integrity audit results, CI/review-state reads, per-PR merge intents/results and new test evidence. Only reviewed source/docs/lock changes are published.

- PR2–8 exact historical-head offline checks passed14/16/18/30/61/84/94 respectively. Review reopened native admission, gateway, policy, toolchain and recovery evidence and source freezes.
- PR9–16 focused adapter checks passed54; reviewer reopened paired native component/JUnit/receipt records and independently verified38 immutable artifacts and their permissions. Earlier attempts and scoped exclusions remain in reports.
- Combined foundation `make test-config` passed255/5.68s under pytest9.0.2; one existing Pydantic graph asyncio deprecation warning.
- PR1: uv0.12.23 `sync --locked` changed only installed pytest; `uv pip check` passed55 installed packages. `UV_OFFLINE=true ... make test-config` under pytest9.0.3 passed255/5.80s with the same warning and retained JUnit.
- The identical synthetic two-test artifact ran three times per source under pytest9.0.3: exactly2 discovered each time, controls6/6 pass, vulnerable security3/3 expected failures, fixed security3/3 passes, no errors/skips. Original device/inode identities checked before all six cleanups; absence confirmed. See the updated [fixture report](../../qualification/native-two-test-fixture.md).

The PR13 retarget API returned an incomplete JSON response. Native server read confirmed base main, unchanged expected head and still-open draft before continuation; no blind merge retry occurred. Dependency branch merge conflicts were retained in session evidence and resolved before validation. Local uv initially reported0.11.12, so lock generation used the repository CI-pinned0.12.23 explicitly. Review-agent default-cache permission failure was preparation-only and corrected with an explicit writable cache. The final record-check command initially named a nonexistent test_development_records.py (exit4, no tests); corrected test_development_workflow.py passed4/0.03s. No new live cluster, model, durable service or real benchmark workload ran during review; existing raw qualification was audited. This pytest patch does not requalify historical OpenShell images or expand runtime scope.

## Decisions and next steps

PR1's [official release notes](https://docs.pytest.org/en/stable/changelog.html#pytest-9-0-3-2026-04-07) include a temporary-directory symlink fix. The dependency change preserves source/tests and all other pins. Native merge commits preserve the original reviewed ancestry; no policy/TLS/kernel weakening, squash, force push or branch deletion was used.

Complete publication, exact-head CI and PR1 merge under the user's existing authorization, then confirm main CI and remaining open PR inventory. Corpus admission remains checkpointed under PLAN-0021:50 real cases are still unqualified, zero real-case executions. Resume one source/runtime/test pair from saved evidence when development continues. ISSUE-0007 still blocks real-provider composition; ISSUE-0006 still gates broader transfer/reconciliation. Every fresh OpenShell runtime needs storage/kernel/CNI/gateway admission. Do not interpret merged fixture work as a complete investigation graph or production qualification.

## Continuation prompt

```text
Read AGENTS.md, docs/development/CURRENT.md, HANDOFF-0029 and the linked PLAN-0021/ISSUE-0006/ISSUE-0007 records. Inspect branch/source/status and verify GitHub PR1/main CI and merge state from the server; the handoff's preparation snapshot is not a final merge receipt. If publication is complete, resume one bounded real-corpus source/runtime/test admission from saved evidence under the existing authorization. Keep exactly two reviewed tests and execute native discovery/control/security assertions before dispositions. Fresh runtime admission and concrete nonempty source/test/dependency recipe gates are mandatory. Do not connect the blocked real provider or broaden transfer/reconciliation. Preserve failure/cleanup evidence, run proportionate checks, update records and append a new handoff.
```
