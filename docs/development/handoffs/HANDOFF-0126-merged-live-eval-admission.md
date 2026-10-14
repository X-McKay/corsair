---
id: HANDOFF-0126
kind: handoff
title: PR130 merged and live evaluation admission
status: recorded
updated: 2026-10-13
related: [SPEC-0078, PLAN-0093]
---

# PR130 merged and live evaluation admission

## Verified state

User accepted the recommendation to merge PR #130, run live agent evaluations on RIG0 after merge, and adopt outcome-blind artifact-bound validity review plus both native probes, with witnesses optional. Trustworthy target-not-reached evidence blocks a conclusion; optional recording is not a prerequisite for adopting the rule.

Verified b7c7340c5e8b3605ceaec2c8db7379b8a7a23201 was green and mergeable, then merged PR #130 with head matching enforced. GitHub reports merge df5c661242c0a833ab481803e116dc5add016e96 on 2026-10-13. Its tree matches the PR head. Host is RIG0. Prepared isolated detached worktree /tmp/corsair-pr130-live at the merge commit; original unrelated HANDOFF-0118/0119 and CURRENT paragraph remain untouched.

## Validation and blockers

No new live evaluations ran. Automatic approval review rejected the proposed six-suite command before execution. It judged the user's general proceed instruction insufficient to authorize sending repository-derived prompts and fixture/source data to the configured external destination https://llm.almckay.io/v1. No retry or workaround followed. Explicit payload-and-destination approval is required by that rejection. Earlier offline/scripted validation remains in HANDOFF-0125; merge is not live qualification.

Existing operator config /tmp/corsair-review-provider.json selects Qwen3.6-35B-A3B-NVFP4 at that endpoint with 180-second provider timeout, 8192 response tokens and 2048 thinking tokens. Config was not changed. Promoted development-live baselines exist in /home/al/git/corsair/.runs/evals for planning (20261013T132359Z-development-live) and assessment (20261013T112140Z-development-live); none found there for authoring or unit sets. Recorded baseline provider settings use 16384 max_tokens, so comparisons with current settings require a comparability caveat, alongside prompt/config/budget differences. Do not silently alter operator settings or automatically promote new baselines.

## Decisions and next steps

After explicit authorization for the destination and payload, run planning, authoring and assessment with SET=unit and SET=development using the existing native eval wrapper, sequentially to avoid concurrent benchmark load. Evaluate the exact merged checkout; retain evidence outside /tmp under the original worktree's ignored .runs. Copy baseline summaries/pointers read-only into the new evidence root for comparison rather than changing the main checkout's baseline registry. Report measured failures and absent baselines. Do not use campaign verdicts as qualified until live results have been reviewed.

## Continuation prompt

```text
Read AGENTS.md, CURRENT.md, PLAN-0093 and HANDOFF-0126. PR130 is merged at df5c661; verify remote state. Preserve unrelated review records. Live evaluation was rejected before execution and needs explicit user authorization to transmit repository-derived evaluation prompts and fixture/source data to https://llm.almckay.io/v1. After authorization, use the existing config and exact-merge worktree /tmp/corsair-pr130-live, run the six isolated suites sequentially, retain evidence under ignored .runs, compare available promoted baselines with configuration caveats, and report failures honestly. No automatic baseline promotion, deployment or further merge is authorized by this handoff.
```
