---
id: HANDOFF-0039
kind: handoff
title: ISSUE-0007 evidence reassessment after PR22
status: recorded
updated: 2026-10-12
related: [HANDOFF-0038, HANDOFF-0034, PLAN-0023, PLAN-0018, SPEC-0023, ISSUE-0007]
---

# ISSUE-0007 evidence reassessment after PR22

## Verified state

Starting local/remote main was clean at `05f0946dba22a4b693f50f2df557744c49ff415b`. PR22 is merged. This checkpoint revisits the issue and implements the next bounded data-preparation slice; resolve its published revision from Git.

Retained evidence is present locally: all55 source-v12 frozen copies match, all8 completed live010 receipts match report input digests, and all8 report inputs match the frozen augmented fixtures. The analyst skill hash matches live010; agent/contracts/provider/source-tool files differ. Historical failures remain relevant but do not qualify the current runtime. The legacy promptv4 seed predates the skill file and cannot receive an invented skill identity.

Implemented: three independently reviewed defect labels with output and skill hashes, exact receipt names, documented output serialization and provenance/coverage limits. The legacy label has its exact output identity and remains excluded. Updated ISSUE-0007 and plans distinguish recovered evidence availability from unfinished calibration. Private derived outputs and provenance remain under `.runs/issue-0007-reassessment-20261012/`; original evidence was not modified. No application or agent runtime code changed.

## Validation and blockers

Focused rubric checks:6 passed/0.36s. Full offline suite (configuration/unit/agents and fixture Temporal contracts/composition):369 passed/6.26s, one existing event-loop deprecation warning; log retained privately. Whitespace review passed before final validation. Independent prior review findings were matched to actual retained outputs by root; no new independent agent review was dispatched. Three known defects are not a balanced or exhaustive label set. No clean labels were inferred from finite passes.

The historical live010 inputs include dependency references absent from the public dataset; future calibration must pair exact saved inputs with output and receipt identity. No exploratory/confirmation split or judge profile was admitted, no inference or runtime dispatched, and no cleanup was needed. ISSUE-0007 remains blocked; the reviewer and analyst/reviewer composition remain unqualified. HANDOFF-0034 retains runtime/corpus state, with zero real-case executions.

## Decisions and next steps

Complete independently reviewed labels including clean examples and failure attribution, then freeze disjoint exploratory/confirmation sets and concrete judge budgets. Use exact retained input/profile evidence, never a case-name lookup against changed inputs. Follow PLAN-0023 before candidate scoring, preserve historical failures and unknown loaded weights, and run a newly frozen integrated-source baseline before claiming current-runtime behavior. The user also requested an explanation of the analyst's expected inputs, desired output and actual behavior; distinguish this read-only stage from the separate reviewer and future test author.

## Continuation prompt

```text
Read AGENTS.md, CURRENT.md, ISSUE-0007, PLAN-0023 and evals/issue_analysis/README.md. Verify main and private evidence. Continue the bounded calibration data work: reviewed positive and negative per-output labels, exact retained input/profile pairing, then disjoint exploratory/confirmation sets. The current three identified defects do not admit judge scoring. Preserve failed attempts and pre-skill history; do not infer current-source qualification from old runs or offline checks. Run proportionate checks, update records and append a handoff.
```
