# Intake quality improvement

Status: implementation authorized by the user's request to improve intake, 2026-10-28. This is a bounded correction within the accepted single-agent intake design, not a new architecture or model/provider change.

## Boundary and hypotheses

Keep canonical native Pydantic output, available-image-only recommendations, one ADK episode, source admission, sandboxing and deterministic policy/scoring. Keep the existing eight-case candidate cohort, hashes, labels, model, endpoint and budgets unchanged. Do not add JSON repair or recipe gates.

The recorded failures show scope/requirements confusion when inventory is absent, missed provided context and two schema-invalid outputs without useful validation categories. The prompt underspecifies independence of issue understanding from environment support and the meaning of unknown requirements. Native source tracking also accepts a reader's explicit truncation flag as a full read; this is a separate grounding bug.

Approach: fix the concrete source-grounding bug, add content-free schema diagnostics, bind native JSON MIME output, and test one clarified prompt variant against frozen cases. Larger alternatives (splitting roles, replacing output contracts, changing provider/model or deriving all analysis in code) are excluded from this change.

## Steps

- [x] Reproduce truncation and schema-diagnostic defects with native ADK regression tests; verify native SDK receives the canonical schema.
- [x] Fix grounding and diagnostics without changing wire fields or evidence authority. Test affected native/unit consumers.
- [x] Explicit native JSON completion and a compact packet: canonical issue appears once; trusted source preload is clearly identified.
- [x] Clarify semantic sequence and category definitions independent of image availability; no case-specific answers or oracle examples.
- [x] Run the unchanged live cohort sequentially at the authorized endpoint under distinct resource identities; retain baseline and failed variants. Repeat final candidate before stating improvement.
- [x] Fresh scoped review; fix important findings with regressions; run `just check`, offline/native tests, wheel build and resource loading outside checkout.
- [x] Record actual results, limitations and unrun gates. Leave unrelated dirty changes and all work uncommitted.

## Baseline

The preceding reviewed run scored 1/8 exact, 2/8 classification, two invalid outputs and zero false-supported. Supported recall was 0/3. These are authored candidate cases pending human review, not a population baseline. Model: Qwen3.6-35B-A3B-NVFP4 at the operator-selected `llm.almckay.io`; no provider substitution or budget increase is planned.

## Executed checks and retained control

Five new regressions were observed failing before their fixes: explicitly truncated preload and tool reads, content-free native schema error categories, native JSON MIME, and the single canonical issue packet with explicit inspected paths. The complete native scripted intake file now passes **11 tests**. No schema repair, extra model loop or permission was added.

- `nix develop --command env TERM=xterm-256color just -- test -q -W error`: **322 passed, 81 deselected**, 12.55s, no warnings/skips.
- `nix develop --command just check`: pinned Ruff/format, Just formatting, ty with warnings failing and local documentation checks passed.
- `CORSAIR_TEST_DOCKER=1 CORSAIR_TEST_TEMPORAL=1 CORSAIR_TEST_NODE_IMAGE=corsair-node:evolution-20261025 CORSAIR_TEST_JAVA_IMAGE=corsair-java:evolution-20261025 .venv/bin/python -m pytest -q -W error -m 'not live' tests/integration/test_execution_chain.py tests/integration/test_execution_sandbox.py tests/integration/test_intake_chain.py tests/integration/test_intake_inspection.py tests/workflow/test_intake.py tests/replay/test_legacy_history.py`: **11 passed, 1 deselected**, 27.68s. Real Docker/Temporal and scripted native ADK; no live-chain reliability implication. Existing local candidate Node/Java tags were used, without pulls or retagging.

The fresh control used the previous wheel extracted into a private directory and imported through `PYTHONPATH` using the root interpreter. Every packaged source/resource byte was checked against the prechange tree. This kept its code/resources fixed while candidate work proceeded. Same eight synthetic inputs, frozen inventories/oracles, provider/model and 60-second episodes: **0/8 exact**, **3/8 classification**, **2 invalid outputs**, **1 model failure**, **0 false-supported**. The preceding 1/8 result is retained separately rather than substituted. Private complete report: `.runs/intake-improvement-20261028/control.json`.

A fresh read-only scoped reviewer found no important/critical code issues. Its minor prompt finding was fixed before use: only non-out-of-scope reports gain a missing-location reason; out-of-scope reports use only `OUTSIDE_SCOPE_POLICY`. Review did not consume private model reasoning or oracle labels.

The structure-only variant retained the original prompt and scored **1/8 exact**, **3/8 classification**, **3 invalid outputs**, **0 model failures**, **0 false-supported**. Two invalid outputs were categorized `schema:value_error`; one modified the supplied canonical issue. The run is retained at `.runs/intake-improvement-20261028/structure.json`, resource identity `689b645f25a7b05848a26ac2172b9bff5a6d118023efa95ce156fc02955c60ed`. This does not demonstrate a completion-quality improvement.

The reviewed prompt variant makes the inspection preload explicit; defines surfaces, modes and requirement categories; separates scope from image availability; distinguishes known-empty requirements from unresolved requirements; and preserves canonical issue data. No case IDs, fixture-specific answers, source literals or oracle labels were placed in the prompt. The final variant is being evaluated with two repetitions (16 attempts) on the unchanged eight-case cohort. The structural phase completed before the prompt resource changed, preserving one resource identity per run.

## Final result, 2026-10-28

The final unchanged cohort completed **16/16 attempts**: **14/16 exact**, **16/16 correct decisions**, **0 invalid outputs**, **0 model failures**, **0 false-supported**. Repeat one scored 6/8 exact; repeat two 8/8. Supported recall was 6/6 across these repeats; the two missing-context decisions correctly remained `needs_input`. The exact mismatches were a raw-JSON report labelled `application` instead of the expected function surface and an out-of-scope report with the wrong execution-mode category. All candidate input/source/inventory/settings digests and 60-second episode ceilings were checked against the control. Native schema bytes, model, provider, frozen fixture bytes and scoring were unchanged.

Final private report: `.runs/intake-improvement-20261028/candidate.json`. Resource identity: `4623709f565e67b469c0926827c3b5567f0450d3f97e501232a0f7f15883c3d2`; control identity: `7ba73b93fc7243ba70050ba20b52e1c8cf9234d5fb31e03975c5b6d53f059c2e`; settings digest in all reports: `f74593b812bfba726f3407f60f0dd6d7e15388a8e7df16f4dbf6d72ae9a59342`.

Each live variant used `.venv/bin/python -m corsair.evaluation.intake evals/datasets/intake-capabilities.json --settings .state/intake-improvement-20261028/settings.json --seconds 60 --repeats N --output PATH`, with explicitly authorized provider configuration. Control imported the frozen package through `PYTHONPATH`; structure/candidate used the current installed editable package. N was 1, 1 and 2, respectively. Logs/reports remain private. These genuine ADK plus real inspection-Docker diagnostics use frozen hypothetical inventories, not physical image-admission qualification. Unknown cost remains unknown. No competing live requests ran during these measurements.

Final offline suite after prompt installation: **322 passed, 81 deselected**, 11.97s; includes installed-wheel resources loaded outside checkout. Final Docker/Temporal/replay repetition: **11 passed, 1 deselected**, 28.14s. `nix develop --command just build` succeeded; its existing warning reports uv 0.13.4 outside the declared uv-build range. Both distributions contain 147 entries with no private/cache paths; all wheel source/resource bytes match the final source tree. No dependencies or build ranges changed.

This is a descriptive improvement on a tiny authored candidate cohort, not a causal isolation of individual prompt rules, held-out accuracy, population safety or baseline promotion. Human-reviewed held-out data, more repeat evidence and current-tree Linux/CI remain unrun. V3 producer/full-live-chain failures in ISSUE-0015 are unchanged; no full-chain model rerun was needed for this intake-only scope. All work remains local and uncommitted; no images were pulled, built or retagged. See [the sanitized experiment](../../../evals/experiments/2026-10-28-intake-quality.md).
