---
id: PLAN-0050
kind: plan
title: CPython 3.7 toolchain image and older pytest
status: complete
updated: 2026-10-13
related: [SPEC-0046, SPEC-0033, SPEC-0037]
---

# CPython 3.7 toolchain image and older pytest

## Objective and dependencies

Implement [SPEC-0046](../specs/SPEC-0046-cpython37-toolchain.md): a CPython 3.7 image row and pytest 6 to 7 support in the runner, parser and probe, qualified live on RIG0. Depends on the kind cluster and OpenShell on RIG0 (one thread at a time) and on SPEC-0042's matrix (draft PR #48) for the row. The JDK 8 image is built in parallel by another thread; shared files (matrix, `prepare_toolchains.py`, `test_toolchains.py`, CURRENT.md) are coordinated by message.

## Steps

- [x] Record real pytest 4.6.11, 5.4.3, 6.0.2, 6.2.5, 7.0.1, 7.2.0 and 7.4.4 output on CPython 3.7.17 with the operator prefix and check the runner and parser against it.
- [x] Make the probe load on 3.7 and pytest 6+, record an unsupported runtime and refuse it by name; regenerate the evidence-assessment set.
- [x] Add `deploy/qualification/toolchains/python37`, per-directory receipts, `TOOLCHAINS=` selection and the 3.7 gate; build it offline locally.
- [x] Add `make qualify-python37-case` for CVE-2021-32839 and let the workspace bound be raised to 512 entries by the operator.
- [x] Live on RIG0: fresh kind node; re-prepare the existing `python` and `java` images too, since per-directory receipts change every receipt digest (a mismatch there is the receipt format, not a source change); `TOOLCHAINS=python37` build, load and gate; `make qualify-python37-case`; `make qualify-witness`, because the probe bytes and schema changed for 3.12 as well.
- [x] Assessment baseline: re-run the scripted evidence-assessment eval on RIG0 and promote it with `make eval-baseline AGENT=assessment` against the pre-#55 baseline; if a live assessment baseline exists by then, re-run it on the regenerated set and compare.
- [x] Add the `cpython-3.7-pytest` matrix row and a pytest framework row scoped to it with the gate report as evidence; the SPEC-0042 report regeneration needs fetched trees and stays pending (stored requirements reselected instead).
- [x] Review, CURRENT.md, handoff ([HANDOFF-0068](../handoffs/HANDOFF-0068-cpython37-toolchain-qualified.md)).

## Validation and progress

2026-10-13, cloud container (not qualification). Real output: 6.0.2 to 7.4.4 discover both ids (6.x in another order), run with exit 1, and parse to control passed, security failed `AssertionError` at `tests/test_case.py:14`; baseline summaries are admitted by `frameworks.py` unchanged. 4.6.11 and 5.4.3 exit 4 on `--import-mode=importlib`. The same driver on CPython 3.12.3 with pytest 6.2.5, 7.4.4, 8.3.5 and 9.0.3 admitted the witness (path reached, effect observed) after the hook-wrapper change; on 3.7 every version ran the tests with the probe injected and recorded `CPython 3.7.17 has no sys.monitoring (3.12+)`. Before the change, the probe would crash the 3.7 bootstrap (`sys.monitoring` missing) and lose the run.

Image: `docker build --network=none` of the python37 context from `python@sha256:b53f496c…` (CPython 3.7.17, pip 23.0.1) installed the nine hash-pinned wheels; fixture control passed (`tests="1"`, `test_native_roundtrip`); syntax, no-tests and assertion exits 2, 5 and 1. `prepare_toolchains build --language python37` itself stopped at `docker pull` with Docker Hub 429 in the container; it runs on RIG0. CVE-2021-32839 host fetch in the container reproduced both #42 manifest digests exactly.

`make test-config`: 997 passed on 6be1b5f before the gate files; 1064 passed after merging main 42a7273 with everything above.

Al's review of 72b6861 (P2): `TOOLCHAINS` reached pytest as a `-k` substring, so `TOOLCHAINS=python` also selected the 3.7 gate and `"python java"` was an invalid expression (exit 4). Fixed with exact `--toolchain` selection from marker arguments; collection-only regressions in `tests/configuration/test_toolchain_selection.py`.

Review of 1ba724f (Hold, records only). The frozen evidence-assessment set (`cases.yaml`, `held_out.json`) was regenerated and re-frozen with `--freeze-held-out`, mechanically: only the schema string, probe digest, witness artifact hashes and the new `"unsupported": null` field changed, but those are agent-visible and `dataset_sha256` changes (development b614014f… to 22773b81…), so earlier assessment baselines are not comparable by hash. Scripted development comparison in the container (not a baseline): main f6a87d6 and this branch 1ede65d both 51/51 clean, identical assertion and repeat-agreement tables; mean input tokens 6105.3 to 6134.0 (+0.5%, the longer record). Held-out and live runs not run here. `evals/evidence_assessment/evaluate.py` also changes on #49 and #58 (merged): whichever of #49 and #55 merges later regenerates the set and re-runs this comparison. #44 (f48b004) also changes the probe, SPEC-0033 and the set: whichever of #44 and #55 merges second resolves the probe, regenerates and re-freezes the set, and `make qualify-witness` runs after both. The SPEC-0033 qualified probe remains the pre-#55 `corsair-witness-v1` digest (PLAN-0039, `.runs/witness-20261013T042451`) until `make qualify-witness` passes on this branch.

2026-10-13, RIG0, worktree `.worktrees/claude/toolchain-python37-drklks`, fresh cluster after `make kind-down` in the JDK 8 worktree. At 93a0fab: `make tools kind-up`, `qualify-network` (`py37-network-20261013T131142Z`, 3 passed), `admission-artifacts admission-install qualify-admission` (`py37-admission-20261013T131451Z`, 1 passed), `openshell-install`, `toolchain-images toolchain-images-load TOOLCHAINS="python python37"`. Gate 1 attempt 1 (`py37-toolchain-20261013T131750Z`) failed: CPython 3.7 keeps a relative `sys.path` entry's `__file__` relative, so the cold-install check's absolute-prefix assertion failed; fixed in #86 (794a003 on 93a0fab, merged c4ea946). Attempt 2 (`…133252Z`, 794a003) errored in setup: the previous gate's cleanup had removed the gateway and `owner.json`; `make openshell-install` now runs before every gate. Attempt 3 (`…133347Z`) passed, 188.4 s. Case attempt 1 (`py37-case-20261013T133724Z`) found no admitted ids, because the patch carried the whole upstream test module with parametrized tests; #88 keeps only the two planned methods (4117e3f, merged 2d6b459). Case attempt 2 (`py37-case-20261013T134635Z`, 4117e3f) passed, 104.4 s, witness refused by name at both commits. `make qualify-witness` (`py37-witness-20261013T134900Z`, 4117e3f) passed, 146.7 s, qualifying the v2 probe c89e0d65…. `make eval AGENT=assessment` scripted development `20261013T135139Z-development-scripted` 51/51 clean, promoted (no earlier run on this set and mode). Results and identities in [the toolchain report](../../qualification/openshell-toolchains.md#spec-0046-cpython-37-image-real-case-and-witness-v2-probe-2026-10-13); evidence archived to `/home/al/git/corsair/.runs/py37-toolchain-20261013/` (1363 files). The cluster was handed to #49's thread and is still owned by this worktree until `make kind-down` runs there.

Matrix rows (evidence-only PR from main bb4f3b7): `cpython-3.7-pytest` after the 3.12 row and pytest `==6.0.2 || ==6.2.5 || ==7.0.1 || ==7.2.0 || ==7.4.4` scoped to it. Reselecting the stored requirements in `benchmarks/runtime-requirements.json` moves 15 revisions of 9 Python cases (CVE-2019-1010017, CVE-2021-32839, CVE-2022-24065 fix, CVE-2022-24439, CVE-2022-29217, CVE-2023-23934 fix, CVE-2023-25577 fix, CVE-2023-32681, CVE-2023-34457) from unsupported to this row; `>=3.8,<3.12` stays unsupported (no nearby-version fallback).

## Decisions and next action

Qualified floor pytest 6.0 (importlib mode); witness on 3.7 refused by name rather than a weaker observer; matrix row only after the live gate (under the lighter process adopted 2026-10-13 these rows are `evidence: live`). Next: none in this plan; a 3.7 case's dependency setup belongs to the environment agent.
