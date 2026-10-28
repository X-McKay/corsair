# Agent roles

Corsair uses three bounded native ADK roles. [Intake](intake.md) normalizes an issue, inspects admitted source and recommends a currently available image. After supported intake in [new investigations](../guides/investigations.md), the producer proposes a canonical `TestPlan`, and an independent outcome-blind auditor returns categorical `PlanAudit` decisions.

The producer has read-only sandbox source readers and can author test files and commands as data. Trusted Docker execution runs accepted plans; the agent has no direct execution tool. The auditor receives issue, bounded source context and the complete plan, with no process observations, evaluator labels or previous outcomes. It can veto semantic validity but cannot create factual evidence or authorize permissions.

Mandatory sandbox source preload is accounted separately from model-requested reads. Grounded source locations must have been read without truncation. Native output schemas are canonical Pydantic class objects. No custom agent loop or JSON repair is involved; Temporal owns revisions and root budgets.

Execution success describes native process behavior. V3 security assessment remains `UNRESOLVED`. Generated assertions, reports and output cannot certify their own correctness.

Historical producer/auditor factories and private procedural skills remain for v1/v2 frozen evaluations and replay. Those factories propose JSON payload pairs for fixed disclosure observers. Their canonical schemas and historical semantics are preserved; they are not the default new investigation path. See [tools and skills](tools-and-skills.md) for that legacy surface and [the investigation guide](../guides/investigations.md) for current execution.
