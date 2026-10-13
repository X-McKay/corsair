---
id: SPEC-0050
kind: spec
title: Assessment witness grounding across repeats
status: accepted
updated: 2026-10-13
related: [SPEC-0030, SPEC-0035, PLAN-0054]
---

# Assessment witness grounding across repeats

## Goal and scope

Review and improve the isolated evidence assessment agent after PR47. Conclusive proposals must retain citations for the observed repeats on which a revision conclusion depends. Existing per-revision citation checks accept one witness even when multiple witness-bearing runs exist.

## Boundaries and design

Keep the existing explicit PydanticAI factory, native output correction, narrow read_evidence tool and deterministic assess/admit authority. For reproduced/not_reproduced require witness item citations for every baseline run whose trusted run evidence carries a witness. For verified require that coverage on both revisions. Match item revision and run index, not item counts; duplicate witnesses from one run cannot stand in for another. An incomplete run without a typed witness requires no invented citation and does not erase an earlier valid reproduction; the gate still blocks fix verification. Do not expose typed gate evidence or labels to the model.

This is a small correction to the existing application provenance rule; no shared framework, SDK wrapper, new tool or provider protocol is needed. Native SDK correction machinery is unchanged.

## Acceptance and validation

Native FunctionModel checks refuse partial multi-run citations and admit complete citations on baseline and candidate; preserve cited baseline reproduction alongside an incomplete repeat. Independently test the evaluator on partial/complete repeat coverage derived from development inputs. Freeze corpus and held-out manifest; compare the same development set to the base run. Scripted checks establish plumbing and evaluator sensitivity, not semantic quality or live qualification.

## Decisions and open questions

User-authorized comprehensive review across active agents; PLAN-0054 records this lane. Live provider comparison is unrun because the root's automatic approval review rejected fixture export outside interpreted host scope; no bypass or provider call is attempted here.
