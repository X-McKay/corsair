---
id: SPEC-0016
kind: spec
title: Local issue-analysis provider qualification
status: accepted
updated: 2026-10-12
related: [PLAN-0018, SPEC-0014, ISSUE-0007]
---

# Local issue-analysis provider qualification

## Goal and scope

Exercise the existing read-only issue-analysis factory against the user-authorized local inference endpoint `https://llm.almckay.io`, using only saved synthetic issue/source fixtures. User explicitly authorized inference and stated there is no cost. No provider billing measurement follows from that statement. The [investigation contract](../../investigation-contract.md), [architecture](../../architecture.md) and [evaluation contract](../../evaluation-and-acceptance.md) remain authoritative.

The native provider boundary, real typed output, source-read behavior, finite semantic checks, failures, usage and local traces are in scope. OpenShell, private repository inputs/secrets, service provisioning, finding/fix verification, hosted telemetry and the full graph are excluded. Shared dependencies/publication remain root-owned. Native durable agent qualification is an independently owned lane.

## Boundaries and design

Use native `OpenAIChatModel`, `OpenAIProvider`, `AsyncOpenAI` and the existing factory/domain contracts. Model and HTTPS base URL are explicitly configured. The explicit OpenAIModelProfile uses native SDK prompted output and InlineDefsJsonSchemaTransformer after measured native tool-output/JSON grammar composition failures; read_source remains the sole function tool. It disables native response/object grammar and strict-tool definitions and merges leading system messages with supported profile flags; all source/domain/output validation remains unchanged. No JSON repair or contract relaxation is admitted. Disable SDK transport retries (`max_retries=0`) and fallback; retain TLS verification, finite time/request/tool/token budgets and native model errors. Anonymous endpoint access uses an explicit inert local credential placeholder; actual operator credentials, if later required, are read only from the named configured environment variable and never printed or persisted. The injectable native HTTP client is an offline-test seam, not a production TLS setting.

Model discovery is read-only and must identify an unambiguous operator-selected model before inference. Saved fixtures and evaluator labels stay separate. Native Pydantic Evals runs finite reviewed semantic predicates rather than requiring exact oracle prose. Preserve every report/output/error/usage observation; absence of usage or traces is unknown/coverage failure. The adapter is composition glue, not a new model protocol or retry framework.

## Acceptance and validation

Offline checks first exercise explicit provider configuration, no automatic paid endpoint/model selection, no hidden transport retries, native structured response parsing, native errors and evaluation negatives. Actual inference then checks a source-grounded path-traversal hypothesis, absent-source missing facts, hostile instructions and a confined-source contrast under unchanged restricted tools. Evaluate entry point/input/operation/effect/preconditions/scope/limitations plus actual native source reads and citations. The lexical predicates are finite smoke gates, supplemented by independent reviewed actual outputs; they are not a general semantic truth oracle. Repeat a small frozen set at concurrency one, retaining attempts, response identity, reported usage, latency, corrections and trace coverage. Small suite results do not establish general correctness/security or tail latency.

## Decisions and open questions

Initial verified TLS discovery `/v1/models` returns exactly one vLLM model: `Qwen3.6-35B-A3B-NVFP4`, root `nvidia/Qwen3.6-35B-A3B-NVFP4`, context limit131072. Model weights/revision digest is not exposed by this result. Root separately observed the serving sparky cache at immutable NVIDIA repository revision491c2f1ea524c639598bf8fa787a93fed5a6fbce and matched public shard blob identities. This is cache provenance, not a byte hash of loaded GPU weights; server args omit revision and loaded identity remains unverified. `/api/tags` returns404; use explicit OpenAI Chat Completions protocol, not a silent protocol fallback.

Native provider [documentation](https://pydantic.dev/docs/ai/models/openai/) and Context7 official `/pydantic/pydantic-ai` identify the supported composition. Root installed the openai extra for pinned slim2.55.0 with OpenAI3.29.0/tiktoken0.14.0 and locked closure. Meaningful factory changes are coordinated with the Temporal owner. [PLAN-0018](../plans/PLAN-0018-local-issue-analysis-provider.md) records actual progress/evidence.


The frozen real-provider assessment observes the typed/source-read boundary but does not meet semantic/consistency acceptance. [ISSUE-0007](../issues/ISSUE-0007-local-issue-analysis-semantics.md) blocks dependent real-agent expansion; [qualification report](../../qualification/issue-analysis-local-provider.md) distinguishes actual failures from finite-rubric false negatives. Full raw native span exports were not retained; report trace identities and completed-case coverage assertions are retained.


## Request-level thinking and communication candidates

A user-authorized continuation adds explicit native request controls on LocalModelConfig: default server behavior, documented non-thinking template kwargs, or a positive `thinking_token_budget` no larger than2048. Disabled thinking and a cap cannot be combined. No inference default, retry, validator, model alias, deployment or overall token cap changes. Native MockTransport checks include actual live run settings and emitted schema descriptions. The selected serving pod's reasoning parser was observed read-only; per-response enforcement and semantic quality still require evidence.

Promptv5 and three schema descriptions clarify the existing read-only task: inventory paths are available through read_source; ready means a cited testable behavioral prediction that may include prevention; only blocking unknowns are missing_facts. Wider-context unknowns remain limitations and environmental assumptions remain preconditions. Source behavior may predict rejection without an execution/refutation/fix-verification verdict. Ordered operations/exceptions and the difference between performing an operation and returning its result are generic analysis guidance. All validation constraints remain unchanged; the change is model-facing communication, not relaxed acceptance. Evaluation labels and independent held-out expectations stay outside model inputs.

The later [SPEC-0019](SPEC-0019-issue-analysis-skills-tools.md) candidate moves general procedural detail into a required native Capability skill and the sole source tool into FunctionToolset. Pydantic input/output contracts, `output_type=IssueAnalysis`, native prompted output parsing/correction and exact current-run citation/scope validators remain the boundary. Explicit response comparisons2048/4096/8192 retain the16000 total and all other limits; no successful smaller-budget claim follows a larger-budget pass.
