---
id: SPEC-0038
kind: spec
title: Whole-repository source tools for read-only agents
status: draft
updated: 2026-10-13
related: [PLAN-0042, HANDOFF-0060, SPEC-0012, SPEC-0014, SPEC-0019, SPEC-0020, SPEC-0022, SPEC-0024, PLAN-0036]
---

# Whole-repository source tools for read-only agents

## Goal and scope

Real benchmark repositories do not fit the SPEC-0014 inline inventory that every read-only stage takes today: at most 16 files and 64 KiB in `source_files`, each file at most 16384 characters (`agents/source/contracts.py`). JSPWiki at the VUL4J-18 baseline has 1,723 files and 14.1 MB. This is gap G2b in the benchmark readiness inventory (IDEA-0005, PR #39). This spec gives a stage a bounded, typed way to find and read source in one captured repository commit, and adopts it first in issue identification (SPEC-0024), the stage that must locate the target in the whole repository.

In scope: a read-only `SourceTree` built from an immutable `SourceSnapshot` (SPEC-0012, `GitSource` capture); three native tools (`list_source`, `search_source`, `read_source`) with operator-owned bounds; per-run byte accounting and read-once handling derived from the run's own messages; a repository mode for issue identification with its own input contract, skill and prompt version; an inline handoff from the tree to stages that still take `source_files`; an offline fixture test suite and a measurement/live smoke harness.

Out of scope: adopting the tools in test planning, authoring, environment or assessment (planning's agent and skill are being changed by PLAN-0038/PR #38; adoption follows it); durable (Temporal) repository mode; repository acquisition (G2c); semantic or AST search; non-UTF-8 source.

## Boundaries and design

**Source view.** `SourceTree` maps confined POSIX paths to byte sizes and loads bytes lazily from the artifact store (`ArtifactStore.get`, which verifies the digest), checking the recorded size. Lines are split on `\n` only, with a trailing `\r` removed, so line numbers match Git, grep and editors; a form feed or other Unicode separator is content. A file is unreadable (and skipped by search, refused by read) when it holds a NUL byte, is not UTF-8, exceeds `file_bytes`, or has a line over 16384 characters (the `SourceLine` bound). The tree carries its `(commit, tree)` identity; the stage's dependencies refuse a tree whose identity differs from the input's repository.

**Tools.** All results are frozen Pydantic contracts with no SDK types.

| Tool | Arguments | Result | Bound |
| --- | --- | --- | --- |
| `list_source` | `directory=''`, optional glob `pattern` | immediate entries with nested file counts and bytes; with a pattern, matching files at any depth (glob against the full path or the file name) | `list_entries` (200); `total` and `truncated` report the rest |
| `search_source` | literal `text` (one line), `directory`, optional `pattern`, `ignore_case` | matches in path order with repository line numbers and trimmed line text, plus total matches, files with matches, files searched and files skipped | `search_matches` (40), `search_line_chars` (240), `query_chars` (200) |
| `read_source` | `path`, `start_line=1` | `SourceRead` of up to 80 numbered lines, ended by the tool at 80 lines, `read_bytes` (16 KiB) or end of file; or `RepeatedRead` when this run already returned the whole window | as listed |

Search is literal substring matching, never a regular expression, so a model-supplied query cannot cause backtracking cost; glob matching uses `fnmatchcase`. Only `read_source` results authorize citations (SPEC-0020): a search match is a location, and the identification finalizer still requires the selected range to be covered by a successful read in the same run and re-reads it from the tree for the quotation.

**Per-run accounting.** The bytes of repository tool results already shown to the model in this run (`model_response_str`) are summed from `ctx.messages` filtered by `run_id`, as the existing finalizers do for reads. A native `prepared` toolset withdraws all three tools once `run_bytes` (128 KiB) is reached, leaving only the output; this is the same structural guard PR #38 uses for the planner. Read-once is the same derivation: a request whose computed window lies inside an earlier read of this run returns a small `RepeatedRead` notice instead of the lines, so a re-read costs almost nothing and does not end the run. No mutable counter lives in the dependencies, so the accounting is deterministic and message-replay safe. Calls issued in one model response are evaluated against the same history and can together exceed the budget by at most one result each.

**Failures.** An invented path, an absent directory, an invalid query or an unreadable file raises `ModelRetry`; with the existing `TOOL_RETRIES = 0` this ends the run at once, as for the inline tools. A call to a withdrawn tool is an unknown-tool failure. Store read and size mismatches propagate as errors, not as empty results.

**Identification repository mode.** `RepositoryIssueInput` holds `case_id` (excluded from the prompt), `issue`, `scope` and `repository` (`commit`, `tree`); the tree itself is supplied in `RepositoryDependencies` with the limits. The prompt adds the root listing, file count and the run byte budget. The skill `identify-issue-repository` tells the model to search first, read candidates and follow a delegation to the deciding method. Output contract and finalizer (`finalize_draft`) are shared with the inline mode, which is otherwise unchanged (`issue-identification-v3`). The repository mode is versioned separately (`issue-identification-repository-v1`, config v1). Explicit mode selection: a separate factory and dependency type, no fallback between inline and repository source.

**Handoff.** `SourceTree.source_files(paths, limits)` materialises selected files as a SPEC-0014 inventory for stages that still take `source_files`, enforcing the same 16-file, 64 KiB and 16384-character bounds. On JSPWiki 96 of 1,723 files exceed 16384 bytes, so the inline handoff only fits small targets; that limit is the reason later stages need these tools too.

## Acceptance and validation

Offline (`tests/agents/test_repository_source.py`, part of `make test-config`): line semantics, unreadable files, size mismatch, listing counts and caps, literal ordered capped search with skip counts and query refusal, window ends at 80 lines, byte cap and end of file, limit ceilings, snapshot tree over `LocalArtifacts` with inline handoff and its bound, identity refusal; through the native agent with a scripted model: search then read grounds a target with no case labels in the prompt, search matches alone do not authorize a citation, a repeated window returns `RepeatedRead` and the earlier read still authorizes, earlier runs' reads neither authorize nor count as repeats, a spent budget withdraws every source tool, invented paths end the run, finalizer refusals for scope, symbol and range. The existing inline identification suite must pass unchanged.

Measurement (`evals/repository_identification/evaluate.py measure`): capture JSPWiki f140a2a4 with `GitSource` at the README's limits, build the tree, report the tree profile and the bytes each tool returns on a fixed probe sequence through the real agent and toolset.

Live (`... live --provider-config`): the frozen smoke case on the local model, three repeats, with selection, budget, unknown-tool and provider-usage checks. This is a smoke, not qualification: one case, one repository, issue text not independently reviewed.

## Decisions and open questions

- Literal search instead of regular expressions: no safe timeout exists in the standard library `re`, and a literal plus glob covers declaration lookup. Revisit with a measured need.
- Accounting from messages, not dependency state, so durable mode can later reuse it; durable repository mode needs a serialisable tree reference resolved inside the activity and is left open.
- Lines split on `\n` in repository mode, unlike `str.splitlines` in the inline reader; the inline mode is left unchanged to keep its frozen evaluations valid.
- Non-UTF-8 files (19 on JSPWiki, mostly Latin-1 resources) are skipped and counted, not decoded with a guessed encoding.
- Open: adoption by planning (after PR #38), authoring, environment and assessment; whether `run_bytes` 128 KiB suits every stage; a reviewed issue text for the JSPWiki case.
