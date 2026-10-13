---
id: SPEC-0049
kind: spec
title: Authoring structural evaluation
status: accepted
updated: 2026-10-13
related: [SPEC-0028, SPEC-0044, PLAN-0053, SPEC-0049, ISSUE-0006]
---

# Authoring structural evaluation

## Goal and scope

Correct false positives in authoring structural evaluation under SPEC-0028 and SPEC-0044. A target call or planned literal/assertion hidden only in a deferred body must not score as direct test-body evidence. Visible os process-creation families must be refused by the existing evaluator. No new agent, runtime, authority, execution or semantic-proof claim is introduced.

## Boundaries and design

Reuse the author's existing AST traversal used for assertion-line admission. Apply it to evaluator target calls, security literals and planned AssertionError lines. Negative control-literal checking keeps a whole-function walk, including nested helpers that may run. Extend the explicit os process-call set to the documented spawn/exec variants, posix_spawn/posix_spawnp and forkpty. This is a small correction to existing deterministic facts; native SDKs do not evaluate these Python AST contracts.

## Acceptance and validation

Regressions cover uncalled nested functions, class methods and lambdas, executable target calls, deferred adversarial literals/assertions, os aliases, direct imports and extracted attributes. The frozen six-case suite remains unchanged and is compared with the base scripted result. Full offline guards cover affected consumers. No generated code executes on the host.

## Decisions and open questions

Names are structural matches, not binding resolution. Deferred helpers called later are conservatively excluded; class bodies/defaults/decorators are not analyzed as an execution model. Dead branches, generator laziness, indirect aliases and assertion intent remain review/replay concerns. The process fact covers listed imports and explicit os attribute/member bindings; posix.system and indirect os.__dict__/vars access remain outside the existing checker. PR49 owns witness admission and prompt v6; integrate after independent review without duplicating that work.
