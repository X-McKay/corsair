# ISSUE-0014: Node/Java assessment live quality

## Status and scope

Open; candidate cohorts are diagnostic and unpromoted. PLAN-0127 implements the scoped paired outcomes and narrow Node/Java recipes, not general-language vulnerability assessment or negative clearance. Native observer conformance and full-live agent quality are separate gates.

## Preserved first full-live repeat

The four-case `node-java-assessments.json` batch completed all four child workflows, but the external scorer accepted no completed assessment (0/4, four incomplete, no operational failure or unavailable result). This is a failed quality gate, not a successful negative conclusion. Cost was unknown.

Saved typed records show a Node control/violation pair vetoed by an insufficient-context audit, a Node held/held pair with rejected audit, subsequent producer abstentions, a Java candidate that did not yield an admitted pair, and invalid Java controls. Native execution did not authorize an assessment where the semantic or completed-protocol gates failed. Raw payloads, explanations and evidence remain private under `.runs/`.

An implementation review found stale Python-only wording in the auditor's always-on instructions. That wording was corrected to name the declared Python, Node ESM and Java recipes; the first native model-request regression verifies delivery. This creates a distinct instruction identity. The initial cohort remains retained and is not rewritten as qualification of the corrected identity.

## Required follow-up

1. Preserve exact frozen cases, source/recipe/image/prompt identities, all attempts, missing usage and unknown cost. Candidate exact-match scores do not measure semantic equivalence or exploit accuracy.
2. Diagnose control construction, source-grounded hypotheses and outcome-blind semantic review separately. Audits must judge coherent test proposals, not demand an already observed exploit or repair a materially false hypothesis.
3. Evaluate the corrected auditor independently before discussing composed quality. Record any subsequent full-live repeat separately.
4. Investigate whether each recipe's bounded protocol admits multiple genuinely source-grounded adversarial candidates. Forced variation, repeated equivalent strings and abstentions must not be counted as completed diverse testing. Do not silently relax the agreed protocol to raise the completion rate.
5. Require actual accepted evidence before `DEMONSTRATED`; require healthy controls and valid, executed held adversarial attempts through the complete admitted protocol before `NOT_DEMONSTRATED`. Missing evidence, rejected audits and abstentions remain incomplete.

Do not close the issue based on scripted native ADK, Docker/Temporal conformance, report generation, prompt delivery or one passing model repeat. New model/prompt/runtime changes need distinct identities and affected requalification.

## Final corrected-instruction repeat

Independent final auditor diagnostics scored 8/12 on preserved Python candidates and 8/12 on new Node/Java candidates; earlier 11/12 and 8/12 stage scores remain retained. Producer diagnostics remained 2/9 and 1/12 respectively. Exact-match diagnostics do not prove semantic equivalence or exploit accuracy.

The distinct final-identity live repeat completed all four workflows and resolved **1/4** assessments: node01 produced a healthy control, native disclosure and accepted audit (`DEMONSTRATED`). Three remained incomplete, including one Java trusted-probe execution error; the remaining cases included insufficient-context audits and invalid controls. No negative result was fabricated. The two healthy held Java pairs were still not sufficient without semantic acceptance. Cost remains unknown. The implementation's 285 passing native tests do not close this issue or establish the goal of majority resolved model-driven assessments.

## Probe attribution and semantic-precedence follow-up

[The separate investigation](../../../evals/experiments/2026-10-26-probe-auditor-consistency.md) attributed the historical Java error to a redundant directory in the producer's relative payload. Hardened-Docker regression preserves the bad path as `ERROR` and validates the correctly composed path as a disclosure; no observer or exception policy was weakened.

The revised auditor matched **20/20** unchanged Node/Java fixture decisions, versus **15/20** under the baseline guidance (including one baseline provider failure). The preserved Python safety cohort remained **12/12**, including rejection of both false-claim cases. However, the final producer exact-match diagnostic remained **5/20**, with two provider failures; java01 addressed the declared fixture in only **2/5** proposals. Concrete prompt guidance does not reliably prevent that error.

One fresh full-live four-case batch then completed **4/4** assessments: Node/Java vulnerable cases were `DEMONSTRATED`, and both guarded cases were `NOT_DEMONSTRATED` only after two distinct admitted executed held rounds with healthy controls, accepted audits, coverage and confirmed cleanup. The committed evidence was independently reconciled and re-scored. The earlier 0/4 and 1/4 batches remain preserved; this one successful repeat is not a population or majority-reliability result. Cost remains unknown.

The final physical-Mac native suite passed **289 tests, zero skips** with explicit reviewed immutable image selectors. A preceding misconfigured selector sweep (273 passed, 16 failed) remains retained. Current-working-tree Linux/remote CI remains unrun. This issue stays **open and unpromoted**: repeated composed reliability, producer control/path quality and human-reviewed held-out cohorts remain outstanding.

## Producer skill and pure-helper experiment

The [separate skill/tool experiment](../../../evals/experiments/2026-10-26-producer-skills-and-tools.md) implements two pure producer helpers without changing the auditor, canonical submission, Docker evidence or finite protocol. Five-repeat Node/Java diagnostics yielded **12/20 exact matches and 16/20 valid native pairs** with the helper surface, versus **4/20 exact matches and 8/20 valid native pairs** for the same revised skill alone. Native replay of the prior 5/20-exact-match proposals yielded 8/20 valid pairs. All original attempts/errors were retained; alternative valid candidates were distinguished from exact-string mismatches without changing oracles.

Neither live arm made a model-requested tool call, so helper execution cannot be credited for the difference. java01 still produced a valid pair in only 2/5 attempts. Preserved auditor safety remained 12/12; the separate Python producer run retained an execution error and did not establish non-regression.

One new full live batch completed only **2/4** assessments: java01 was DEMONSTRATED and java02 was NOT_DEMONSTRATED after both admitted held rounds. node01 abstained, then produced a native adversarial execution error; node02 had a healthy held first round, then abstained before protocol completion. Neither Node case received negative clearance. The failed full-chain gate and measured slower helper-surface median episode latency remain recorded. This issue remains **open and unpromoted**; improved small-cohort proposal validity is not established end-to-end reliability or speedup.
