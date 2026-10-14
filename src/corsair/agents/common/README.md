# agents/common

Small helpers every v2 agent package shares. Keep this directory small: a helper lands here only when a second
agent needs it.

| Module | What it does |
| --- | --- |
| `usage.py` | `run_recorded(agent, name, prompt, ...)` runs one native agent and returns `(output or None, AgentUsage)`; `to_agent_usage` maps native `RunUsage`, leaving unreported values `None` |
| `prompted_output.py` | `prompted_output()` hook: keep exactly one JSON object from a prompted-mode answer |
| `budget.py` | `tool_budget()`: withdraw domain tools once the run's native `UsageLimits.tool_calls_limit` is reached |
