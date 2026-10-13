---
id: HANDOFF-0102
kind: handoff
title: UI data connections and Kubernetes packaging
status: recorded
updated: 2026-10-13
related: [SPEC-0072, PLAN-0079]
---

# UI data connections and Kubernetes packaging

## Verified state

Worktree `/home/al/.codex/worktrees/corsair-ui/corsair`, branch `codex/corsair-ui`, PR107. Source started at 7d8517b; main 184e609 is already merged. Resolve this handoff's publication revision through git. Primary checkout remains untouched.

The UI has real filesystem evaluation projections, native Temporal parent-investigation status, native Temporal/OpenShell service checks and source-status reporting. Separate source paths and producer `CORSAIR_EVAL_RESULTS` support shared storage. Missing mounts return503; no sample records ship. Frontend refreshes visible pages and displays actionable failures. Pinned Gunicorn container and explicit Kubernetes renderer use an existing read-only results PVC, actual runtime matrix and optional existing service TLS Secrets. No launch/configuration mutation UI is introduced.

The user selected Kubernetes alongside Corsair. Infrastructure connection values remain operator-owned; no automatic discovery, new run database or worker deployment is invented. See the [runbook](../../runbooks/local-ui.md) for actual commands and settings.

## Validation and blockers

The plan retains actual commands/failure history. 85 focused backend/producer/deployment tests passed; 18 UI unit tests/build and 64 browser checks passed with 8 duplicate mobile contrast checks skipped. Actual scripted identification evaluation: 16/16 clean attempts. Final production image 8d8805a11b516277d93093adae0a464af5f6eb4579d9b0033652e9582cbeef52 served that report and exact native distributions through separate read-only mounts; missing storage returned 503. Owned smoke containers removed with absence confirmed. Browser Agents/System inspected with real saved records; the earlier external design mockup is illustrative only and is not part of the application/image.

No live target-cluster deployment, successful Temporal/OpenShell connection or ingress authentication qualified. Missing endpoints display Not configured. CI adds the real-producer image smoke. Final offline suite and publication status are recorded in PLAN-0079; verify current GitHub checks rather than inferring them from local evidence. Logs and actual run reports remain ignored/outside Git.

## Decisions and next steps

Review/merge PR107 under the user's existing process; do not merge without current authorization. To deploy, select the actual image, namespace, shared producer PVC, native endpoints and TLS identity Secrets, render resources, and validate source/service status on that cluster. The UI cannot fabricate historical metrics that upstream reports never recorded. Follow existing live model/sandbox qualification separately.

## Continuation prompt

```text
Read AGENTS.md, docs/development/CURRENT.md, SPEC-0072, PLAN-0079 and HANDOFF-0102. Inspect git/source state on codex/corsair-ui and PR107. Use Corsair development/review skills. Confirm final CI and any review findings; keep production data connections read-only and distinguish saved/scripted evidence from live service/workload qualification. For an authorized deployment, use actual operator-selected namespace/PVC/endpoints/TLS Secrets and verify a newly produced report plus native service checks. Never seed sample results or report missing metrics as zero. Run relevant checks, preserve actual evidence outside Git, update records and leave a new handoff.
```
