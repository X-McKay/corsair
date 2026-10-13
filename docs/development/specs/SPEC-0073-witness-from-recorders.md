---
id: SPEC-0073
kind: spec
title: Witness requests bound by the framework table's recorders for real issues
status: draft
updated: 2026-10-13
related: [SPEC-0033, SPEC-0040, PLAN-0079, PLAN-0083]
---

# Witness requests bound by the framework table's recorders for real issues

## Goal and scope

A witness request (`WitnessRequest`: target file, target symbol, effect file name) is today an operator envelope
written for one case; the chain uses it only when the identification names exactly its target and the plan's
security witness is its effect. Only the SPEC-0018 fixture has one, so a real issue started through
`corsair run` requests no witness and the assessor sees outcomes only. This spec lets the operator's recorders for
the selected framework bind the request instead, from agent outputs that are already admitted, under rules that
are the table's and not per case. Excluded: new recorder kinds, the probe itself, changes to what planning may
plan, binding the full subject path at execution (SPEC-0040, PLAN-0082).

## Boundaries and design

- `FixtureCase.witness_from_recorders` (default false): the run may bind a request from
  `environment.witness_facilities`, the operator facilities the framework table declares (`corsair.investigation.
  frameworks`; pytest's `audit_open`, file opens). `corsair run` sets it; the fixture keeps its envelope.
- `witness_request(identification, envelope, planned, recorders)`: an envelope, when present, decides exactly as
  before. Without one, the request is `WitnessRequest(target.source.path, target.symbol, planned.subject)` and is
  refused unless the identification is ready, the planned facility is one of `recorders` with the planned effect as
  its kind, that effect is one the probe records (`file_open`), and the subject is a plain file name (the probe
  matches names, so `a/b.txt` would name another path). A refusal runs the revisions without a witness and records
  the reason, as today.
- What the agents choose is bounded by what they cannot change: the target is the admitted identification's
  (grounded in a successful source read), the subject is the plan's sentinel inside the operator scratch location,
  the probe and its record format are operator code, and the gates still need the effect observed in the control and
  absent in the security test on each revision. Labels and expected outcomes never reach the request.

## Acceptance and validation

Offline: a request binds exactly the identified target and planned subject when a listed recorder covers the planned
effect; a missing recorder, another kind, an effect the probe does not record or a directory-prefixed subject is
refused; an envelope still decides when present. Live: a corpus case through `corsair run` reaches execution with a
witness request and the probe's record admitted on both revisions.

## Decisions and open questions

The operator no longer approves the concrete target per case: a mistaken identification probes the wrong function,
which shows as a witness that does not confirm, never as a confirmation. A plain-name subject can match an
unrelated open of the same name inside the probed call; PLAN-0082's subject binding narrows that later.
