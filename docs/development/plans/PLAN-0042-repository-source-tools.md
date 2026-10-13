---
id: PLAN-0042
kind: plan
title: Whole-repository source tools
status: in_progress
updated: 2026-10-13
related: [SPEC-0038, HANDOFF-0060, SPEC-0024, SPEC-0012, PLAN-0036]
---

# Whole-repository source tools

## Objective and dependencies

Implement [SPEC-0038](../specs/SPEC-0038-repository-source-tools.md): bounded list, search and read tools over a captured repository commit, adopted first by issue identification, so real benchmark repositories (gap G2b in IDEA-0005, PR #39) can be analysed. Started under Al's 2026-10-13 instruction to continue until every example and benchmark can be tested. Independent of the kind cluster. Planning adoption waits for PR #38 (it changes `agents/test_planning/agent.py` and its skill); this plan does not touch those files or any file PR #39 changes.

## Steps

- [x] `SourceTree` over `SourceSnapshot` + `ArtifactStore`, inline fixture constructor, Git line semantics, unreadable-file handling, inline handoff (`agents/source/repository.py`).
- [x] Native toolset `list_source` / `search_source` / `read_source` with operator limits, message-derived byte budget and read-once notice, withdrawn through `prepared` when spent (`agents/source/repository_tools.py`).
- [x] Identification repository mode: input contract, dependencies with identity check, prompt, skill, factory; shared finalizer extracted from the inline mode (`agents/issue_analysis/repository_identification.py`, `identification.py`).
- [x] Offline tests over a fixture tree and through the native agent (`tests/agents/test_repository_source.py`).
- [x] Measurement harness and JSPWiki smoke case (`evals/repository_identification/`); measured in the container.
- [ ] Live smoke on the local model on RIG0 (three repeats).
- [ ] Adopt in test planning after PR #38 merges, then authoring, environment and assessment, each with its eval set rerun.
- [ ] Durable repository mode: a serialisable tree reference resolved inside the activity.

## Validation and progress

2026-10-13, container, branch `claude/repo-scale-source-tools-l7bldu` from main `334aa03`:

- `make test-config`: baseline 853 passed before changes; see HANDOFF-0060 for the count with this change.
- `tests/agents/test_repository_source.py`: 19 passed.
- Measurement: full bare clone of `https://github.com/apache/jspwiki` (124 MB), `evals/repository_identification/evaluate.py measure`. `GitSource` captured f140a2a4 (tree d8f10520) in 19.3 s under the README limits. Tree: 1,723 files, 14,129,990 bytes; 1,471 readable text files with 250,486 lines (largest 14,522 lines); unreadable: 231 binary, 19 non-UTF-8, 1 over 1 MiB, 1 with a line over 16384 characters; 96 files exceed the 16384-character inline file bound. Probe (seven calls through the real agent and toolset, 0.16 s): root listing 1,222 B, `*WikiServlet*.java` 312 B, search `getForwardPage` in `*.java` 966 B, case-insensitive `forward` 2,734 B (capped at 40 matches), two 80-line reads 1,619 B and 843 B, repeated window 248 B (`RepeatedRead`); 7,944 B of the 131,072 B run budget; prompt 1,114 B. The scripted final selection `DefaultURLConstructor.getForwardPage` 278–281 was quoted from the tree.
- Live smoke: unrun at this point.

## Decisions and next action

Decisions are recorded in SPEC-0038. Next: run the live smoke on RIG0 and record it; then planning adoption once PR #38 is merged. Stop if the live smoke shows the tools are unusable by the local model (for example every attempt exhausting the budget), and record that instead of tuning prompts in this plan.
