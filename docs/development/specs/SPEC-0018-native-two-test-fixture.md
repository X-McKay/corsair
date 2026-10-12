---
id: SPEC-0018
kind: spec
title: Native two-test fixture semantics
status: accepted
updated: 2026-10-12
related: [PLAN-0020, PLAN-0019]
---

# Native two-test fixture semantics

## Goal and scope

Qualify manually drafted test semantics using the existing reviewed synthetic path-traversal source and its confined counterpart. This independent component requires no real-model integration or new runner. Follow the investigation contract: exactly one benign control and one safe-behavior security regression, unchanged test bytes across both source variants, actual native pytest discovery/execution, individual outcomes and real filesystem witnesses.

## Boundaries and design

Use fresh local temporary fixture workspaces and the locked Python3.12/pytest9.0.2 environment. These short repository-owned source files are reviewed scratch-only code; no downloaded repository, untrusted build script, exploit suite, external network or credentials are executed. This is explicit local fixture execution, not a sandbox security boundary, OpenShell qualification, model-authored test qualification or a real-project benchmark. Variants and expected results are evaluator-only material.

## Acceptance and validation

The control reads an allowed sentinel through the real function. The probe requests a readable outside sentinel still inside scratch. Native Python audit events record actual opens without mocking the application or sink. The fixed function must raise its specific ValueError before opening outside; other errors, skipped discovery and failed setup are not security success. Original source bytes stay unchanged. Frozen tests must pass control on both variants, fail the security assertion on vulnerable and pass on fixed, with three fresh repeats and native JUnit/stdout witnesses. A finite fixture outcome does not authorize an application finding/fix disposition elsewhere.

## Decisions and open questions

Broader native repository recipes, benchmark admission and model-authored drafts remain separate gates.
