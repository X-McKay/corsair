# Model and ticket provider configuration

Copy [the example](../../config/examples/providers.json) to an operator-owned file and replace the endpoints, model IDs and repository. Model inference and ticket sourcing are independent settings. Do not put secret values in this file; store it outside agent workspaces.

## Models by agent

`inference.models` defines complete, reusable profiles. `inference.agents` selects a profile for each agent; `inference.default` is used only when an agent has no explicit selection. Omitting the default requires each used agent to be named. Unknown agent names, unknown profiles and missing selections fail before model requests. There is no fallback after errors. Switching a profile replaces the entire provider/model/settings tuple.

Agent keys are `identification`, `repository_identification`, `environment`, `planning`, `authoring`, and `assessment`. A model profile supports:

- `vllm`: the existing HTTPS `/v1` OpenAI Chat Completions path and measured vLLM-specific settings (`thinking_mode`, `thinking_token_budget`, response cap and timeout).
- `openai_compatible`: explicit HTTPS `/v1` endpoint and model name; optional `api_key_env` (omission explicitly means anonymous), response cap, timeout and optional temperature. Uses native OpenAI Chat Completions with conservative tool-output capabilities. It does not send vLLM thinking extensions. The chosen endpoint/model must support the agent's tool calling; protocol compatibility alone does not establish agent quality.
- `bedrock`: explicit `region` and model/inference-profile ID, optional `aws_profile`, response cap, timeout and optional temperature. Uses native PydanticAI Bedrock Converse and boto3's credential chain (profile, environment, workload role). No AWS secrets are serialized in the config. SDK inference retries are disabled; unavailable access/model/region fails without switching providers. AWS service endpoints are selected by the native regional client, not environment endpoint overrides. Credentials may be resolved by the native AWS chain before requests. Model-specific unsupported settings are surfaced by the native provider/service.

Resolved per-agent profiles and native model identities are recorded by the chain evaluators; isolated evals record their selected profile. Credential *names* are configuration, not credential values. Changing provider does not change tools, prompts, budgets or contracts, and does not automatically promote an evaluation baseline.

```sh
make eval AGENT=planning PROVIDER_CONFIG=/absolute/path/providers.json
make eval AGENT=authoring PROVIDER_CONFIG=/absolute/path/providers.json
PYTHONPATH=src:. .venv/bin/python -m evals.fixture_chain.evaluate \
  --evidence .runs/mixed-provider-chain --provider-config /absolute/path/providers.json \
  --live identification,planning,authoring,assessment
```

The chain's `--temporal-address` selects its existing durable route with the same per-agent instances registered on the worker; credentials and clients never enter workflow payloads. `evals.fixture_e2e.run` and the OpenShell fixture gate use the same resolution. Existing `LocalModelConfig` JSON and imports continue to work as one shared vLLM profile. Existing stage-profile JSON still overrides only request controls; vLLM-only controls are rejected for other providers. The historical `evals.issue_analysis.live` CLI remains explicitly vLLM-only.

`corsair.inference.models.agent_models(config, agents)` is the reusable application context manager, while `configured_model(config.resolve('environment'))` serves a single agent. Environment selection is supported by its isolated eval; this change does not connect the environment agent into the currently incomplete full real-case chain.

## Ticket sources

GitHub example: `{"provider":"github","repository":"owner/repo","token_env":"CORSAIR_GITHUB_TOKEN"}`. Omit `token_env` for public unauthenticated reads. This initial adapter targets github.com issues (not PRs or GitHub Enterprise).

For Azure DevOps Services replace only `tickets`:

```json
{"provider":"azure_devops","organization":"example","project":"Security Project",
 "token_env":"CORSAIR_AZURE_DEVOPS_TOKEN","auth":"pat"}
```

`auth: "bearer"` accepts an operator-supplied Entra access token instead. Token renewal is external; no credential broker or automatic fallback is introduced. Azure DevOps Server/on-premises endpoints are outside this initial adapter.

```sh
PYTHONPATH=src:. .venv/bin/python -m corsair.tickets.capture \
  --config /absolute/path/providers.json --ticket 123 --output .runs/ticket-123.json
```

The parent output directory must exist. Capture creates an exclusive mode-0600 file; existing files are refused before dispatch. A failed capture leaves an empty file, never an admitted partial snapshot. Successful files contain a typed snapshot and SHA-256. Treat description/comments (including HTML) as untrusted text, never render/execute or obey them as instructions. Tickets never choose repository, revision, scope, runtime or provider authority.

Adapters retain title, description, state, source/revision, timestamps, comment IDs/authors/formats and discussion. Comments are paginated under default limits of 10 pages and 1 MiB decoded response bytes for the complete capture; `max_pages`, `max_bytes` and `timeout_seconds` are operator settings. Exceeding a limit fails, not truncates. HTTP errors carry provider, code, status and an action; response bodies/headers and credentials are excluded from error text. Redirects are refused. Ticket revision is checked again after pagination; separate API requests still cannot promise atomicity against every concurrent comment edit. Snapshots record observation time rather than claiming a transactional revision of the entire discussion.

`corsair.tickets.inputs.identification_input(snapshot, scope=..., source_files=...)` builds the existing typed identification input from operator-supplied source/scope. It refuses content beyond the 8192-character stage budget; it never silently drops discussion. Ticket capture does not automatically fetch a repository or launch a sandbox investigation.

## Validation and qualification

Transport tests use HTTP mocks; inference tests use native SDK mock transports and Bedrock Stubber. These demonstrate configuration, mapping, pagination, tool translation and failure boundaries, not live service access or model correctness. Live inference and authenticated GitHub/Azure capture remain unqualified until separately run with an authorized endpoint, model, identity and read target. No hosted-model spend is triggered by installing or validating this configuration.

API references: [GitHub issues](https://docs.github.com/en/rest/issues/issues#get-an-issue), [GitHub comments](https://docs.github.com/en/rest/issues/comments#list-issue-comments), [Azure work items](https://learn.microsoft.com/en-us/rest/api/azure/devops/wit/work-items/get-work-item?view=azure-devops-rest-7.1), [Azure comments](https://learn.microsoft.com/en-us/rest/api/azure/devops/wit/comments/get-comments?view=azure-devops-rest-7.1), [PydanticAI Bedrock](https://ai.pydantic.dev/models/bedrock/).
