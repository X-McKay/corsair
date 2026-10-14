---
id: SPEC-0084
kind: spec
title: Read-only UI over v2 run records and eval runs
status: accepted
updated: 2026-10-14
related: [SPEC-0082, PLAN-0105, HANDOFF-0139]
---

# Read-only UI over v2 run records and eval runs

## Goal and scope

Al (2026-10-14): make the UI branch (PR #107) fully functional, integrated and working with Corsair v2. #107 was built on v1 (`corsair.nodes`, v1 eval summaries, `corsair.chain.Investigation`), none of which exists on develop. This replaces its data layer and pages; the visual design, the read-only boundary and the deployment shape stay.

The UI reads only what v2 writes, never a second store:

- run records, `corsair-v2-run/1` (`src/corsair/RUN_RECORD.md`), from `corsair-v2 run` (`.runs/v2/runs`) and from each chain eval attempt (`<results>/chain/<run>/evidence/runs/<receipt>`);
- eval runs, `corsair-eval-summary/v1` (`evals/agent_summary.py`): `summary.json`, `policy.json`, `command.json`, `index.jsonl` and promoted pointers under `.runs/evals`, plus committed baselines beside each agent's cases;
- the v2 runtime matrix (`corsair.matrix.Matrix`), Temporal visibility for `corsair.v2.Investigation`, and OpenShell gateway health.

Excluded: launching, cancelling or promoting anything; message histories, stage outputs, probe output, provider or task-failure text; v1 records.

## Boundaries and design

`src/corsair/web/server.py` projects every value through an allow-list (`plain`, `rollup`, `run_detail`, ...) and reads with directory descriptors and `O_NOFOLLOW` under fixed size limits. Null stays null. The run-row fields and the incomplete-record rule mirror `corsair.runs.row`/`details`; the eval reference mirrors `evals/run.py _v2_reference` (promoted, committed, previous whole-set run). The Temporal workflow id `corsair-v2-<run id>` (corsair.cli) links an execution to its record. OpenShell health uses the UI's own endpoint/TLS settings or, failing that, only the endpoint and TLS paths of `CORSAIR_OPENSHELL_CONFIG`.

Readiness requires assets, a valid matrix and at least one readable record source. The production image carries the `ui` dependency group (gunicorn, PyYAML, pydantic, temporalio, openshell), not the agent stack.

## Acceptance and validation

- API and projection tests over records shaped like the v2 writers' output, including hostile paths, symlinks, oversize files, wrong schema and private text (`tests/ui`).
- The real scripted producer's summary read back unchanged (`tests/ui/test_web_producer.py`).
- Browser tests over a root the real scripted chain and reviewer evals populate (`ui/e2e`).
- CI builds the image and smoke-checks it against a fresh scripted chain eval and its run records.

None of this is live qualification of a deployment, of Temporal or of OpenShell.

## Decisions and open questions

- Experiments page and the v1 metric histograms removed: v2's comparison is the reference comparison `evals/run.py` already defines; histograms over per-attempt samples can return once live baselines exist.
- Open for Al: whether the UI should ever trigger work (no, by default); whether to keep the Aladdin-derived palette from HANDOFF-0101 (kept).
