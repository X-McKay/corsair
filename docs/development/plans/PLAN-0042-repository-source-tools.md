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
- [x] Live smoke on the local model on RIG0 (three repeats); harness fixes from it (selection evaluator, absolute paths).
- [ ] Adopt in test planning after PR #38 merges, then authoring, environment and assessment, each with its eval set rerun.
- [ ] Durable repository mode: a serialisable tree reference resolved inside the activity.

## Validation and progress

2026-10-13, container, branch `claude/repo-scale-source-tools-l7bldu` from main `334aa03`:

- `make test-config`: 853 passed on main before the change; 873 with the first commit (256874e, CI `offline-guards` green); 874 after the harness fix.
- `tests/agents/test_repository_source.py`: 21 passed.
- Measurement: full bare clone of `https://github.com/apache/jspwiki` (124 MB), `evals/repository_identification/evaluate.py measure`. `GitSource` captured f140a2a4 (tree d8f10520) in 19.3 s under the README limits. Tree: 1,723 files, 14,129,990 bytes; 1,471 readable text files with 250,486 lines (largest 14,522 lines); unreadable: 231 binary, 19 non-UTF-8, 1 over 1 MiB, 1 with a line over 16384 characters; 96 files exceed the 16384-character inline file bound. Probe (seven calls through the real agent and toolset, 0.16 s): root listing 1,222 B, `*WikiServlet*.java` 312 B, search `getForwardPage` in `*.java` 966 B, case-insensitive `forward` 2,734 B (capped at 40 matches), two 80-line reads 1,619 B and 843 B, repeated window 248 B (`RepeatedRead`); 7,944 B of the 131,072 B run budget; prompt 1,114 B. The scripted final selection `DefaultURLConstructor.getForwardPage` 278–281 was quoted from the tree.
- RIG0 (worktree `/home/al/git/corsair-repo-tools` at 256874e, full bare clone, evidence `.runs/repository-*-rig0-*`, private): `measure` first failed with a relative `--evidence` path (`LocalArtifacts` needs an absolute root; attempt retained as `repository-measure-rig0-001`), passed with absolute paths as `-002`: same profile as the container, capture 7.2 s, probe 7,944 B.
- Live smoke `repository-live-rig0-001`: Qwen3.6-35B-A3B-NVFP4 via vLLM, 16384 response cap, temperature 0, prompted output; budget 12 requests, 10 tool calls, 160k tokens, 300 s, one output correction. All three attempts began search `class WikiServlet`, read WikiServlet.java at 1 and 80, search `getForwardPage`, then read `URLConstructor.java` and `DefaultURLConstructor.java`. Attempt 1 failed: after eight tool calls (17,609 B returned) the model called a nonexistent tool `status` (its output field name), which ends the run under zero tool retries. Attempts 2 and 3 completed with `ready`, `doGet`, `WikiServlet.java` 88–101, each using 10 of 10 tool calls (about 22.4 KB returned, 11 requests, about 67k input and 1.9k output tokens, 33–34 s), with one `RepeatedRead` each. Budget, unknown-tool and usage checks passed on both. The run did not include the selection evaluator (harness defect, fixed: `live_evaluators`); the stored outputs were rescored afterwards with the same `selection_checks` (see HANDOFF-0060).
- Findings: the tools are usable by the local model; the read-once notice fired as intended; every completed attempt hit the tool-call ceiling exactly, and the model re-read WikiServlet after already reading it; one in three attempts invented a tool. Not qualified: one case, one repository, three attempts.

## Decisions and next action

Decisions are recorded in SPEC-0038. Next: planning adoption once PR #38 is merged. Open questions from the smoke, deliberately not tuned here: a 10-call ceiling is tight for search-then-read on a real repository, and an invented `status` tool call ends the run (a prompted-output model naming its output field); both belong to a broader repository eval set rather than one case.
