# Local issue-analysis provider assessment

The user-authorized local endpoint is `https://llm.almckay.io/v1`; the explicitly selected served model is `Qwen3.6-35B-A3B-NVFP4`. Read the [provider qualification report](../qualification/issue-analysis-local-provider.md), [spec](../development/specs/SPEC-0016-local-issue-analysis-provider.md) and [plan](../development/plans/PLAN-0018-local-issue-analysis-provider.md) before running. This command sends only the repository's saved synthetic issue/source fixtures. It admits no private repository inputs, credentials, shell/network acquisition tools, service deployment or security finding/fix verdict.

Use the locked repository environment. Root owns dependency installation; do not change the lock or install concurrently with other lanes. First run the offline checks:

```bash
PYTHONPATH="$PWD/src:$PWD" UV_CACHE_DIR="$PWD/.cache/uv" \
  .venv/bin/python -m pytest tests/agents -q
```

For a new user-authorized local assessment, choose a new ignored evidence directory; the CLI refuses an existing directory, writes attempt/report files exclusively and never overwrites previous attempts:

```bash
PYTHONPATH="$PWD/src:$PWD" UV_CACHE_DIR="$PWD/.cache/uv" \
  .venv/bin/python -m evals.issue_analysis.live \
  --base-url https://llm.almckay.io/v1 \
  --model Qwen3.6-35B-A3B-NVFP4 \
  --evidence .runs/local-provider-new-attempt --repeat 2
```

The model/profile are explicit; there is no provider fallback. The selected endpoint needs no workload credential: native SDK requests use an inert local placeholder and ignore unrelated OpenAI environment keys/URLs. If authentication becomes required, stop and configure only the intended `CORSAIR_LOCAL_MODEL_API_KEY` through the typed provider configuration; do not print or retain its value. There is no TLS bypass option. HTTP-client injection is an offline MockTransport seam.

The supported native provider profile uses prompted structured output with an inlined schema and one leading system message. This server's automatic strict-tool grammar and final response grammar do not compose for a source-reading run. The SDK handles schema instructions/message placement; Pydantic domain validation, exact source/current-run citation checks, one-based inclusive ranges and zero tool retries still apply; with the separate native tool budget, an invented tool name or a refused read ends the run rather than prompting a correction. The configured server is `vllm`. No JSON repair or per-step scheduler exists.

Every case has a fresh input/dependency state and native run identity, concurrency1, requests4/tool calls2/total tokens16000, response tokens2048 by default (explicit comparison options4096/8192), SDK/task retries0, output correction1, client timeout60s and case timeout180s. Budget changes require a separately frozen, user-authorized comparison with measured completion/quality/usage; never rewrite a prior result or change the rubric to force a pass. Exit1 means task/evaluator/assertion failure; inspect retained reports and actual typed outputs. A typed result with a failed semantic assertion remains a failed semantic result. Independent review must check preconditions, bounded effects, citations and guarded-source/instruction contrasts; finite lexical checks are not a general truth oracle.

Native local Logfire/Pydantic Evals trace identities and completed-case span-coverage assertions, model response IDs, provider-reported usage, attempted tool arguments, corrections and failures are retained without hosted telemetry. Full raw span exports are not retained; failed-case span coverage is not asserted. Missing response usage remains unknown, even if native counters contain zero. Cost is unmeasured; the user's no-cost assertion is not a billing receipt. Freeze source/config/fixtures/lock before comparative runs. Model aliases and cache revision metadata do not prove the identity of loaded GPU weights. No runtime resources are created; native client closure is the only cleanup needed. Parent-owned OpenShell/Temporal qualification has separate procedures.


## Explicit request-level thinking comparisons

The default remains `--thinking-mode server_default`, with no request override. For a separately frozen native Qwen/vLLM comparison, `--thinking-mode disabled` sends only `chat_template_kwargs.enable_thinking=false` through the native SDK. `--thinking-token-budget 768` instead sends the top-level native `thinking_token_budget`; it requires a compatible server reasoning parser/config. These options are mutually exclusive. Thinking budgets are strict positive integers up to2048, independent of the selected response cap; neither thinking option raises the response cap or changes retries, authority or domain validation. Unsupported options/errors do not trigger fallback. Request-body tests cover the exact live settings merge; per-run extra_body replacement by other callers is outside this fixed recipe. The thinking control and the selected response cap are typed `LocalModelConfig` fields merged with temperature0 and no parallel tool calls into one model-level settings mapping; the live runner passes no run-level model settings.

Documentation and startup arguments are prerequisites, not evidence that a budget is enforced. Inspect per-response provider usage and actual output; a reasoning-token total across several responses is not a per-response cap violation. Speculative decoding may affect native budget support. Do not alter the serving deployment to force support. See PLAN-0018 for the retained non-thinking regression and the capped response that completed with incorrect semantics. Prompt and schema descriptions are also part of the frozen model input; record their exact bytes along with provider settings.

The user also authorized larger response budgets when warranted. `--response-token-limit 4096` and `--response-token-limit 8192` are explicit comparison options; the default stays2048, the task total stays16000 and retry/time/request/tool limits stay unchanged. This cap includes reasoning and answer tokens. A pass with a larger cap would not qualify the earlier2048 profile. PLAN-0018 records the repeated truncations motivating this selected budget, along with any remaining semantic failures.

The agent uses Pydantic input/output models and a native async output function as `output_type`. Its flattened `IssueAnalysisDraft` schema accepts line references; scope/current-run read validation and trusted quotation lookup produce the unchanged final `IssueAnalysis`. The model does not generate quotation text. The required procedural skill is loaded from `src/corsair/agents/issue_analysis/skills/analyze-issue/SKILL.md` through native Capability instructions; its hash is in evaluation metadata. The sole native FunctionToolset lives in `tools/source.py`; its read_source returns a Pydantic SourceRead containing numbered SourceLine entries, without duplicated quote text. Those saved-file coordinates, rather than upstream numbers printed in reference text, identify citations. Native correction feedback reports already-read ranges without enlarging authority. This is qualified from a source checkout; including Markdown data in a distributable or deployment image is not yet qualified. Fresh Temporal fixture histories exercise the new toolset identity; compatibility with pre-change histories is untested.


The private ISSUE-0007 reference experiment selected response8192/total32000/requests6/tools4 while retaining output correction1, SDK/task/tool retries0 and client60s/task180s. These are recorded candidate budgets, not the CLI defaults or a qualification recommendation. Eight original attempts completed, but manual semantic errors and two of four failed independent holdouts leave the gate blocked. Retain timeout delivery/usage as unknown for the unanswered request; inspect saved evidence before any new dispatch.


Later private coordinate/numbered-tool comparisons explicitly select response16384/total64000/requests6/tools4/client120s/task300s with unchanged thinking/retry policy. The tracked CLI does not expose that private reference recipe. Consult the assessment and frozen runner rather than copying budgets into a different source/dependency workload. An unanswered request remains uncertain even when later distinct experiments complete; never recast a new candidate as a retry or repair of the prior attempt.
