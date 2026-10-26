# v3 live candidate diagnostics, 2026-10-26

AI-run candidate diagnostics, pending human review. These are not promoted baselines and make no accuracy, false-positive, clearance or production claim (see the [candidate policy](../README.md)).

## Identity

| Item | Value |
| --- | --- |
| Code | `v3-best-of-all-asjtt3` tree at 5f814341: per-agent rows ran on that tree, chain rows on merge d78209ac, whose tree is identical |
| Model | `Qwen3.6-35B-A3B-NVFP4` on the operator's local vLLM endpoint, ADK `LiteLlm` route `hosted_vllm/`, server-default thinking, `request_timeout_seconds` 300 |
| Image | `corsair-python:0.1`, `sha256:d904c88c0ed6ea38ec34fa363ab028b5f96006254de6985ee9477049ad0d7fb7` |
| Runtime | RIG0, local Temporal dev server, one worker, Docker `runc` |
| Budgets | Each frozen request's own budget. The fixtures use `max_rounds` 2, `max_llm_calls` 8, `episode_llm_calls` 3, `max_tool_calls` 12, and `max_output_tokens` 4096 by default |
| Repeats | 3 per case, concurrency 1 |
| Model sharing | Not shared: no other thread was using the model during these runs |

## Results

| Report | Attempts | Pass | Notes |
| --- | ---: | ---: | --- |
| `agent-producer-dev.json` | 3 | 0 | all `no_valid_output`: the producer reads source (3 to 4 tool calls) and runs out of its 3 LLM calls before it submits |
| `agent-producer-expanded.json` | 9 | 0 | same failure on every row |
| `agent-auditor-dev.json` | 6 | 3 | 2 rows stopped on `MAX_TOKENS` (operational), 1 `audit_invalid` |
| `agent-auditor-expanded.json` | 12 | 11 | 1 `audit_invalid` |
| `chain-dev.json` | 9 | 1 | 7 INCONCLUSIVE because the producer budget ran out, 2 ERROR on `MAX_TOKENS`; no pair reached evidence |
| `chain-safety.json` | 6 | 6 | all INCONCLUSIVE, which the safety oracle allows; no pair reached evidence |
| `chain-adversarial.json` | 6 | 2 | 4 ERROR on `MAX_TOKENS`, 2 INCONCLUSIVE |

Across the chain rows no producer submitted a pair, so the kernel ran no evidence, no row reached a decisive label, and the second independent session never started (it needs a first-session clean negative). These rows therefore do not yet exercise `EXPLOIT_DEMONSTRATED`, `EXPLOIT_NOT_DEMONSTRATED` or the session loop with a live model.

## Excluded runs

An earlier set used the `openai/` route. With that route, ADK sends the response schema together with the tools, and vLLM's guided decoding then forbids tool calls. That set is void and is not recorded here. A first 5f814341 chain-dev attempt reused a run id from the void set, and the artifact store refused it with an immutable identity conflict. Dev was rerun under a new run id. Raw reports for all of these stay under the rig's ignored `.runs/live-baselines-20261026/`.
