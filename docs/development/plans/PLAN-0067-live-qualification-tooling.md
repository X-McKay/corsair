---
id: PLAN-0067
kind: plan
title: Live qualification tooling
status: in_progress
updated: 2026-10-13
related: [SPEC-0062, PLAN-0049, PLAN-0050]
---

# Live qualification tooling

## Objective and dependencies

Implement [SPEC-0062](../specs/SPEC-0062-live-qualification-tooling.md). Branch `claude/qualification-tooling-sig4ss` built on PR #51 (merged as `93a0fab`: per-image gates on one module-scoped gateway, pytest root pinned in make targets, merged with #55's `TOOLCHAINS` selection and `qualify-python37-case`).

## Steps

- [x] `qualify_image.py` with `run`, `status`, `archive`; `qualify-image`, `cluster-status`, `archive-runs` targets; `qualify-python37-case` refuses a `CASE` other than its own.
- [x] Stub smoke checks in `make test-config` (`tests/configuration/test_live_harness_smoke.py`, plugin `live_harness_stubs.py`).
- [x] RIG0 allow rules `deploy/rig0/settings.local.json` and their offline check.
- [x] Development guide: tiers, rules, the final-source rule and its cost, four standing decisions. Base-image skill: runbook, row in an evidence-only follow-up PR.
- [ ] First live `make qualify-image` on RIG0 when the cluster queue reaches this thread (after #51, #55's gate, #49, Perl, Node, Ruby, chain hand-off).

## Validation and progress

2026-10-13, cloud container (no Docker daemon, no cluster): the new smoke file passed 16/16. Mutation checks: making `toolchain_gateway` function-scoped fails the one-gateway-per-target check (three installs under `toolchain`); removing the image-case `objects` directory creation fails the image-case check. Every other live test reached its first native call or gateway use under the stubs. `make cluster-status` ran here and reported no receipt and no cluster. Full `make test-config`: see below.

Al's review at `d10dd13` (comment-type): orchestrator and evidence logic sound; before the allow file reaches RIG0, the `qualify-image *` rule admitted extra make goals and shell injection through `TOOLCHAIN`/`CASE` (confirmed with `make -n`), and the deny list lacked `kubectl delete --all` and `rm -rf /`. Fixed in the Makefile guard (one goal, allowed command-line variables only, `TOOLCHAIN` from the image directories, values through the environment), with `--eval`/`-f`/`-I`/`-e` make options denied, all five hook substrings denied, refusal of a named-but-refused evidence run, untracked files counted, and the guide's hook wording corrected; `make -n` cases added to the smoke file.

PR #75 merged as `a162733`. Al's review at `801e756` (posted just before the merge, P2): a truncated or non-object retained `build.json` raised out of `Run.execute()`, so the run left no `SUMMARY.md`. Follow-up: an unreadable, malformed or non-object receipt is now an `image-build` refusal that names the retained path and keeps the cache; regression with `{`, `[]`, `null` and invalid UTF-8 asserts the summary and no image-load or gateway call (fails 4/4 without the fix).

## Decisions and next action

- Network is checked before the gateway install, not after, so a failed network check leaves no unconsumed gateway.
- No generic image-only case target: the Maven harness needs a prepared checkout and test ids; the image-only tier stays the existing commands, documented in the guide.
- Reuse searches only `.runs/qualify/*/` of this checkout (five newest); older manual runs are reused only when named.

Next: Al reviews the allow rules once; the first RIG0 run qualifies the target.
- 2026-10-13 13:55Z, Al chose the lighter path (SPEC-0062 last paragraph). Branch `claude/qualification-process-l4ofi4`: `evidence` on every matrix row (existing rows `live`), `perl-5.26-make` and `tap-harness` added as `image-only` from PLAN-0061/PLAN-0066's Docker runs, development guide and base-image skill rewritten for rows with the PR and a milestone gate batch. The first live `qualify-image` run moves to the first milestone batch.
