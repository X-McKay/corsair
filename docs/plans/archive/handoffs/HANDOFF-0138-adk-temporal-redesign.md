---
id: HANDOFF-0138
kind: handoff
title: ADK and Temporal durable-round redesign
status: implemented
updated: 2026-10-24
related: [PLAN-0105]
---

> Historical record. Commands, counts and status describe the recorded revision, not the current working tree. See [current work](../../README.md) for current guidance.

# ADK and Temporal redesign handoff

## Delivered approach

A from-scratch implementation of the recommended **Plan 1: durable investigation rounds**, on the user-authorized `manus/re-design` branch of X-McKay/corsair. Baseline commit is `d3da7d3f77e6395c795727cb1341f2c81dc69e80`. Main and other branches are unchanged; previous implementation, corpus and records remain in Git history. The old executable v2/OpenShell stack and compatibility paths are intentionally not retained in this branch.

The layout aligns with `agent-playbook/02-reference-architecture.md`: role-local agent metadata/factory/instructions/private tools; shared security capabilities; deterministic Temporal workflows; durable activity steps; runtime assembly and artifacts; one canonical contract module; pure verdict policy; external evaluation and observability; datasets/fixtures/evaluators/experiments/baselines; named test, risk, threat, runbook and deployment directories. Empty catalogs and duplicated schemas were avoided.

Google ADK 2.13.0 supplies native Runner, sessions, callbacks, tool schema, structured output and model connectors. Temporal 1.34.0 supplies durable activity/round coordination, root admission budgets, cancellation, bounded child evaluation, replay and worker recovery. Docker 7.2.0 supplies native container lifecycle and isolation. The implementation does not use Alpha turn-level integration, a provider protocol, custom agent graph, generalized skill engine or custom scheduler.

The supported first slice is `python.secret_disclosure/1`, an operator-defined standard-library Python callable recipe. The producer reads admitted source and submits data payloads and revision metadata. A trusted fixed pytest/coverage observer runs control/adversarial inputs in isolated offline containers and checks for disclosure of a fresh random private fixture. An outcome-blind, tool-free auditor reviews the complete proposed mechanism. Pure policy admits `SUPPORTED` in component scope, `CONDITIONAL` for application claims supported only by component evidence, and `INCONCLUSIVE` for failed reproduction. No negative clearance is implemented. Optional fixed-source testing establishes only that this demonstration was blocked while benign behavior survived.

## Durability and evaluation boundaries

Operations publish immutable execution intents before native side effects. Committed observations reconcile by source, submission, recipe, configuration, image, budget and fixed/original identity. An uncertain intent cannot be blindly replayed. Artifacts are immutable, atomic and hash-checked; a final recording step alone is idempotently retried. Interrupted ADK episodes are not model-call-resumable. Local artifact-host loss requires backups/shared storage in addition to Temporal history.

Saved scoring requires the actual committed native artifact chain and reuses runtime validation plus pure verdict rules. Oracle labels remain outside agent packets and child inputs. Missing or lost usage remains null; completed producer rounds survive later evidence/audit failure. Frozen dev datasets diagnose native, isolated-role and whole-system behavior separately. Human-owned held-out datasets and broader recipes are future work, not implied by tiny authored fixtures.

## Final executed validation

On 2026-10-24, after independent review remediation and cleanup:

```bash
uv run ruff check src tests evals/evaluators
uv run ruff format --check src tests evals/evaluators
DOCKER_HOST=unix:///run/user/1000/docker.sock \
  CORSAIR_TEST_DOCKER=1 CORSAIR_TEST_TEMPORAL=1 \
  CORSAIR_LIVE_CONFIG=.state/live.json \
  uv run --locked --extra providers pytest -q -W error
uv build
```

**Result: 66 passed in 68.63 seconds; no tests skipped or deselected; warnings treated as errors.** Ruff and formatting passed. The wheel and source distribution built. The package test created a fresh environment, installed the actual wheel with SDK dependencies, and verified agent JSON, instructions, risk and trusted driver resources plus the `corsair` console entry point outside the checkout.

This includes real Docker-native vulnerable/safe/fixed evidence, unexpected exception/canned marker/control failure/timeout regressions, immutable cleanup checks, real Temporal workflow/cancellation/restart/history replay, preserved failed-activity forensics, genuine scripted ADK producer/auditor episodes, and actual CLI frozen-batch scoring with real children/native observations. Scripted episodes are not live-model accuracy claims. The ordinary real-provider auditor smoke also ran.

The auditor development experiment exposed acceptance of a false hypothesis. The packaged instruction was improved through the same production factory and frozen external scorer. Both dev fixtures then passed three repeats: **6/6**, with 4,668 input and 604 output tokens; monetary cost was unavailable. See [the sanitized experiment](../../../../evals/experiments/2026-10-24-auditor-hypothesis.md). This is not a statistically meaningful or held-out accuracy result.

Five independent review findings were fixed with regressions: prefixed oracle filenames, forged saved positive scores, unknown usage converted to zero, dropped completed rounds on later activity failure, and a floating base image. See [review remediation](../reviews/review-remediation.md).

## Explicit limitations and blocker

The live security producer request was rejected by the configured provider's `cyber_policy`. It was retained as an operational failure, not reported as a pass, retried with obfuscation or switched to another provider to evade the block. **Live security producer/whole-system model accuracy remains unqualified.** Actual integration coverage uses a labelled scripted ADK model plus genuine Docker and Temporal, not fabricated native observations.

Arbitrary malicious target code can attack in-process Python observation. The pilot's data-only producer and hardened container do not establish universal interpreter/runtime attestation. Admit only operator-authorized, sanitized source on a dedicated disposable host. Production/team deployment, stronger observation/isolation qualification, arbitrary probes/build repair, dependency installation, other languages and application-exposure proof remain deferred.

## Copyable next actions

1. `make sync check test build`; then `make images`, `make test-docker`, and `make test-temporal` on an authorized host.
2. Read [the pilot runbook](../../../operations/runbooks/pilot.md), select the narrow source root and configure worker-side provider/model credentials. Do not assume the example Gemini model is a qualified production recommendation.
3. Run native reference replay before live agents: `corsair verify evals/fixtures/case01/request.json evals/fixtures/case01/submission.json --settings .state/settings.json`.
4. Discuss provider suitability and human-labelled held-out cases before claiming live producer reliability. Use approved provider workflows, not policy evasion.
5. Extend with one genuinely needed recipe at a time. Keep native conformance and explicit evidence/property semantics ahead of generalized infrastructure.

Private provider settings, credentials, raw evidence and raw evaluation reports are excluded from the Git branch. The public committed artifacts are source, lock/config examples, frozen public fixtures, sanitized experiment/qualification records and development documentation.
