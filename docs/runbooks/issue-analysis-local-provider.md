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

The supported native provider profile uses prompted structured output with an inlined schema and one leading system message. This server's automatic strict-tool grammar and final response grammar do not compose for a source-reading run. The SDK handles schema instructions/message placement; Pydantic domain validation, exact source/current-run citation checks, one-based inclusive ranges and zero tool retries still apply. No JSON repair or per-step scheduler exists.

Every case has a fresh input/dependency state and native run identity, concurrency1, requests4/tool calls2/total tokens16000, response tokens2048, SDK/task retries0, output correction1, client timeout60s and case timeout180s. Do not raise these or change fixtures/rubric to force a passing result. Exit1 means task/evaluator/assertion failure; inspect retained reports and actual typed outputs. A typed result with a failed semantic assertion remains a failed semantic result. Independent review must check preconditions, bounded effects, citations and guarded-source/instruction contrasts; finite lexical checks are not a general truth oracle.

Native local Logfire/Pydantic Evals trace identities and completed-case span-coverage assertions, model response IDs, provider-reported usage, attempted tool arguments, corrections and failures are retained without hosted telemetry. Full raw span exports are not retained; failed-case span coverage is not asserted. Missing response usage remains unknown, even if native counters contain zero. Cost is unmeasured; the user's no-cost assertion is not a billing receipt. Freeze source/config/fixtures/lock before comparative runs. Model aliases and cache revision metadata do not prove the identity of loaded GPU weights. No runtime resources are created; native client closure is the only cleanup needed. Parent-owned OpenShell/Temporal qualification has separate procedures.
