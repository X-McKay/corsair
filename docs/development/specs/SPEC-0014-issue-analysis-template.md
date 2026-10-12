---
id: SPEC-0014
kind: spec
title: Read-only issue-analysis fixture template
status: accepted
updated: 2026-10-11
related: [PLAN-0016]
---

# Read-only issue-analysis fixture template

## Goal and scope

Implement one independently runnable PydanticAI issue-analysis template over explicit saved issue/source fixtures under [Milestone 5](../../implementation-plan.md). It proposes a cited, testable hypothesis at component or application-path scope, or records missing information/unsupported requirements. It emits no finding/fix verdict and performs no execution. [Investigation](../../investigation-contract.md), [architecture](../../architecture.md), [execution/recovery](../../execution-and-recovery.md) and [evaluation](../../evaluation-and-acceptance.md) remain authoritative.

User resumption of HANDOFF-0023 authorized independent PydanticAI and Temporal foundations while OpenShell admission continues. This slice excludes live providers/credentials, shell/network tools, workspace source acquisition, OpenShell, durable agent integration and the five-agent graph. Fixture checks cannot establish an application fix or live reasoning quality; exactly two native finding-specific validation tests remain a later gate.

## Boundaries and design

- `IssueAnalysisInput` holds an explicit fixture identity, issue, authorized scope and immutable tuple of source files. Canonical relative POSIX paths (at most 256 characters) are keys, never filesystem paths resolved by an agent. At most 16 files, 16384 characters/file and 65536 aggregate UTF-8 source bytes are admitted. Saved fixtures are operator-loaded; loading arbitrary host files is not an agent capability.
- `FixtureDependencies` holds only that input. One native function tool, `read_source`, returns at most 80 actual lines from a listed key. Missing paths, traversal/absolute/noncanonical keys and invalid/oversized line ranges fail through native tool errors. There is no execution backend because this stage executes no code.
- `IssueAnalysis` is a Pydantic domain output with `ready`, `missing_information` or `unsupported`, hypothesis fields, source citations, missing facts and limitations. Facts are nonempty and at most 2048 characters; lists/citations are limited to 16 entries. Unknown fields—including finding/fix verdicts—are refused. A ready result requires a hypothesis, citations and no missing required facts. Incomplete results require missing facts and no ready hypothesis.
- Under [SPEC-0020](SPEC-0020-issue-analysis-citation-references.md), a native output function accepts Pydantic `IssueAnalysisDraft` line references, admits only the requested scope and ranges actually read in messages stamped with the current native `run_id`, and supplies exact quotations from saved inputs to the unchanged final `IssueAnalysis`. Reads from prior supplied history cannot satisfy current citations. The SDK rejects explicitly reused run IDs already present in history. This establishes structural citation grounding, not semantic truth or completeness of model prose.
- One factory requires an explicit native `Model` instance; no configured provider or fallback is supplied. PydanticAI owns agent execution, typed output, correction limits, overrides and instrumentation. Callers inject native `UsageLimits` at the run call; budgets are not agent-visible editable data. The evaluated configuration limits three model responses, one successful source tool and 5000 total estimated tokens. Native limits do not bound hidden provider retries or all failed tool attempts; none are configured here.
- Native `Instrumentation` excludes prompt, source and tool payload content. Pydantic Evals uses local span capture with `logfire.configure(send_to_logfire=False, console=False)`, no hosted account. SDK objects stay in the agent/evaluation modules; contracts contain no model/workflow SDK objects.

Native async tools/validators/scripted callbacks keep the cheap fixture operations inside the SDK async path. No custom runner, provider protocol, tracing system, graph or repair loop is introduced. The same factory/contracts are the seam for eventual native `TemporalDurability`; no wrapper or durability claim is implemented now.

## Acceptance and validation

Meaningful deterministic checks cover exact source reads and accepted output, native overrides/TestModel/FunctionModel, refusal of arbitrary keys/ranges, uncited/fabricated/scope-expanded output, extra conclusions, native request/tool/token limits, missing facts, model failures and local span coverage. Evaluation oracles remain in a separate file and are supplied to the scripted model by the evaluator; they never enter stage prompts/dependencies/source inputs.

Native Pydantic Evals runs three frozen development cases twice at concurrency one. Oracle equality tests correctness of predetermined contract plumbing; native tool-set and call-budget evaluators test observable trajectory; an explicit chat-span predicate makes absent agent spans a coverage failure. Missing-source and hostile instruction fixtures cover structural robustness/security authority without claiming live prompt-injection resistance. Report actual attempts, errors, durations, model/tool counts and estimated fixture usage; provider billing/revision/compatibility remain unqualified. No held-out semantic reasoning case or population quality estimate is claimed.

## Decisions and open questions

Selected stable release: [PydanticAI v2.55.0](https://github.com/pydantic/pydantic-ai/releases/tag/v2.55.0), immutable commit `7db7a4d8c4b7b7b85b8636cf0b6e3305bafb5167`. Primary [slim metadata](https://pypi.org/pypi/pydantic-ai-slim/2.55.0/json) and [Evals metadata](https://pypi.org/pypi/pydantic-evals/2.55.0/json) require Python >=3.11; slim's temporal extra requires temporalio>=1.27.0. Root selected `pydantic-ai-slim[temporal]==2.55.0`, `pydantic-evals[logfire]==2.55.0` and temporalio 1.34.0. Provider extras are deferred. Slim/evals wheel SHA256 identities are `7fcea628e78c2f247af94504534f0577151496166998d74ec145505040b19c68` and `78e07e9ece6c36e1232c3141537584d402b15d29a82080f50e50ec869719b301`.

Context7's official `/pydantic/pydantic-ai` discovery and primary immutable sources informed the design. Actual installed APIs supersede stale examples: instrumentation is now a capability, Dataset requires a name and result usage is a property. [Native testing](https://pydantic.dev/docs/ai/guides/testing/), [native agentic evaluators](https://pydantic.dev/docs/ai/evals/evaluators/agentic/) and [native Temporal integration](https://pydantic.dev/docs/ai/capabilities/durable_execution/temporal/) describe the reusable seams. New durable code should use `TemporalDurability`, `PydanticAIWorkflow`, `PydanticAIPlugin`; `TemporalAgent` is deprecated. Compatibility is only researched/imported here, not durably exercised by this component.
