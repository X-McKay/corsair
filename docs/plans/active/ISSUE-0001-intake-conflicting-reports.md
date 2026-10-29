# Intake can select a finding from contradictory reports

Status: open, observed 2026-10-29; no fix or quality qualification claimed.

The frozen `conflicting-reports` JSON candidate contains the same issue ID with two unresolved reports: a path-traversal security claim and a cosmetic rename request explicitly reporting no security defect. Intake's reviewed instructions require an unresolved conflicting report to abstain rather than choose a record. In the live Qwen diagnostic it selected the security report, recommended an image and classified the issue `in_scope_supported`. The frozen candidate oracle expects no classification and no image. This is one false-supported result relative to that authored candidate oracle; the cohort remains pending human review.

Observed configuration/resource identities and exact command are in [PLAN-0004](../archive/plans/PLAN-0004-intake-qwen-route-evaluation.md). Source/input/oracle bytes and labels were not changed. The outgoing-schema correction addresses valid native tool transport, not this semantic selection failure. Preserve the failure in every future evaluation denominator.

A supported intake decision is not a security verdict. The main investigation still requires an operator Case binding, committed source/image selection and native evidence. This diagnostic does not qualify autonomous scanner normalization or automatic execution based on all heterogeneous inputs.

Before closing: assess a bounded agent/policy correction without scanner-specific key allowlists or exposing the oracle to the model; repeat the unchanged original and JSON cohorts, retain all other failures and configuration identities, and test the production workflow stop for unresolved contradictory reports. Do not rewrite labels or automatically promote a baseline to close this issue.
