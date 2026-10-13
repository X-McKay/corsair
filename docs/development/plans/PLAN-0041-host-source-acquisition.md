---
id: PLAN-0041
kind: plan
title: Host acquisition of exact benchmark commits
status: complete
updated: 2026-10-13
related: [SPEC-0037, SPEC-0012, SPEC-0025, PLAN-0021]
---

# Host acquisition of exact benchmark commits

## Objective and dependencies

Implement [SPEC-0037](../specs/SPEC-0037-host-source-acquisition.md): a host step that fetches each benchmark case's fix commit at its exact SHA, verifies and measures it, and hands a typed `FetchTarget` on to the SPEC-0025 sandbox fetch. This is IDEA-0005 step 2 (gap G2c), proposed in the benchmark readiness inventory on the separate `claude/benchmark-readiness-7xbmvr` branch. No dependency on the kind cluster, the local model or that branch; the sandbox fetch itself stays blocked on the workspace storage quota.

## Steps

- [x] Adapter `src/corsair/adapters/git_acquire.py` (`GitAcquisition`, `HostTransport`, `AcquireLimits`, `TreeStats`, `AcquiredSource`) with offline tests `tests/unit/test_git_acquire.py`.
- [x] Case resolver and runner `evals/benchmark/sources.py`; resolver and pins consistency checks `tests/configuration/test_benchmark_sources.py`.
- [x] Smoke: two cases (JSPWiki, dot-prop) end to end, including `GitSource` capture of fix and parent.
- [x] Network run of all resolved cases; commit `benchmarks/source-pins.json`.
- [x] Format-only fsck downgrade (`fsck_warn`) after the first run refused six repositories; rerun of those cases.
- [x] Review, CURRENT.md row, handoff ([HANDOFF-0059](../handoffs/HANDOFF-0059-host-source-acquisition.md)), draft PR.

## Validation and progress

Offline: `uv run --locked python -m pytest tests/unit/test_git_acquire.py` 11 passed; `make test-config` 866 passed (853 on main plus 13 new). The first draft failed three of its own tests, each a real finding fixed in the adapter or test: `git init` copied sample hooks larger than a small file-size limit (now `--template=`), a file-size kill surfaces as `index-pack died of signal 25` with fetch exit 128 rather than a signal exit (now classified `budget`), and a test fixture's `\0100` octal escape.

Smoke (2026-10-13, cloud container through its egress proxy, `.runs/acquire-smoke/`): JSPWiki fix `88d89d65` acquired with complete ancestry in 7.4 s, 54,258,721 repository bytes, 1,724 files / 14,132,441 bytes; single parent `f140a2a4`, matching the hand acquisition recorded in PLAN-0021 (54,258,800 bytes then; this smoke still copied Git's sample hooks, and the template-free full run measured 54,232,587); `GitSource` captured both at the largest admitted ceilings (1,724 and 1,723 files). dot-prop 89,558 bytes, 15 files.

A first full run was stopped after two cases to rerun on the final adapter (template-free init); its partial output is kept as `.runs/acquire-20261013-superseded/`.

Full run (2026-10-13, `.runs/acquire-20261013/`, default limits: complete ancestry, 600 s, 2 GiB repository, 4 GiB memory, strict fsck): 40 cases resolved, 10 unresolved (no fix reference; 5 of them also without a repository). 33 acquired, 7 refused. Six refusals were `transfer.fsckObjects` rejecting historical objects whose hashes still verify: werkzeug ×2 (`missingSpaceBeforeEmail`), requests and rails (`badTimezone`), sanitize and sinatra (`zeroPaddedFilemode`). The first adapter classified them as `transport`; they are now `source_admission` with the message ids kept. One was `host_network`: salsa.debian.org (CVE-2023-31486, whose fix lives in Debian's perl packaging repository, not the inventory's HTTP-Tiny repository) is refused by this container's egress proxy (`CONNECT tunnel failed, response 403`); it was not attempted elsewhere.

Rerun of those seven with `--fsck-warn badTimezone missingSpaceBeforeEmail zeroPaddedFilemode` (`.runs/acquire-20261013-fsck-warn/`): six acquired with their warnings recorded, salsa refused again the same way. The pins file holds the rerun's records for those cases; the first run's refusals stay in its receipts.

Result, all in `benchmarks/source-pins.json`: 39 of 40 resolvable cases acquired with verified commits. Largest repository rails 209 MB (4,413 files, 27.5 MB tree, 46 s); 33 of 39 repositories are under 30 MB. Six fixes are merge commits (bleach, cookiecutter, werkzeug ×2, @vivaxy/here, sanitize), so no single-parent baseline candidate is recorded for them. `GitSource` at its largest admitted ceilings (4,096 files, 16 MiB per file, 64 MiB total, 60 s, 512 MiB) captured the fix commit for 28 cases and refused 11: file count over 4,096 (struts ×2, tomee), symlinks or a submodule (cookiecutter, GitPython; rails also has a symlink), and its own `fsck --strict` exit 4 on the format-only messages above (werkzeug ×2, requests, sanitize, sinatra; rails exceeded the 4 KiB stderr budget on the same messages).

## Decisions and next action

Complete ancestry by default, not shallow, because the qualified `GitSource` capture refuses shallow repositories; `--depth` stays available as an explicit measure-only mode. Fetch from the repository named in the fix reference and flag disagreement with the inventory's `repository_url`, rather than guessing. The runner deletes fetched repositories and captured objects after recording unless `--keep`; receipts stay. Downgrading format-only fsck messages is opt-in and limited to three ids; `GitSource` keeps refusing them, so capturing those six cases needs a separate decision on SPEC-0012 (the same downgrade there, or a capture that does not walk ancestry). Next: repository-scale source access (IDEA-0005 G2b) for the cases over the capture ceilings, and the SPEC-0025 sandbox fetch once the storage quota is qualified.
