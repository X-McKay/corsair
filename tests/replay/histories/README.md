# Retained replay histories

Each JSON file is a Temporal workflow history replayed by [`tests/replay/test_history.py`](../test_history.py)
against the current workflow code. A history proves that a workflow change keeps replaying executions recorded by an
earlier version; it is not evidence about a target, a model, or a verdict.

| History | Recorded by | Activities |
| --- | --- | --- |
| `pre-sessions-lone-clean-negative.json` | `InvestigationWorkflow` before the `independent-sessions-v1` patch gate | The test double `FakeActivities` in [`tests/workflow/temporal.py`](../../workflow/temporal.py) |
| `evaluation-counts-only.json` | `EvaluationWorkflow` before its status query listed child rows | The same test double, through child investigations |

Both histories come from the synthetic test double, not from a model or a real sandbox, so their activity payloads are
the double's fixed values.

## Payload patches

- **2026-10-26, closed audit rule.** `AuditResult.rule` became the closed `AuditRule` enum (`R1` to `R4`, `ALL`) bound
  to the decision (`ACCEPT` if and only if `ALL`). The double used to answer every audit with the free-form rule
  `independent-evidence-review`, which no longer decodes. The double now answers `ALL` for its acceptance, and the
  same value was patched into every base64 payload that carried the old rule: the audit activity result, the record
  activity input and result, and the workflow result (four payloads) in `pre-sessions-lone-clean-negative.json`, and
  the two child investigation results in `evaluation-counts-only.json`. Only that one JSON field changed; event order,
  commands, markers and every other payload byte are as recorded.
