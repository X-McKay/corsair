# Data flow

An investigation turns an operator-admitted request into a bounded sequence of payload proposals, differential runs, coverage checks, blind reviews, and an immutable labelled result. Models propose a payload pair and may reject one; they cannot run code, see an outcome, or turn an observation into a label. The kernel gates below run in a fixed order, and each gate that fails stops the investigation at its own label.

```text
request + settings
      │
      ▼
prepare ──► manifest + immutable admitted source snapshot
      │
      ▼
pre-model gates: target_binding → ast_guard → build_replay
      │
      ▼  (one producer session per bounded Temporal round)
producer ADK episode ──► Submission (benign/exploit payload pair)
      │
      ▼
kernel materializes the recipe with the proposed payloads (immutable intent)
      │
      ▼
differential pair: control_run + control_coverage, exploit_run + exploit_coverage
      │
      ▼
evidence_agreement ──► verified Observation
      │
      ▼
blind_audit (auditor ADK episode; pair only, never an outcome; reject-only)
      │
      ▼
fixed_differential (fix revision: control holds, demonstration no longer occurs)
      │
      ▼
verdict table in code ──► one of six labels ──► immutable result artifact
```

## 1. Admission and run identity

The request identifies the recipe, the finding (file, exact target line, CWE), a bounded budget, the source to admit, and an optional fix revision. `prepare` resolves the configured immutable image identity, then admits the source through the local snapshot adapter. Admission uses descriptor/no-follow checks, rejects unsafe/sensitive entries, produces deterministic bounded archive bytes, and can enforce an expected digest. The resulting `PreparedCase` refers to an artifact rather than a live checkout path.

A `RunManifest` records request/configuration identity, image ID, model names, prompt and agent-spec digests, output-schema digests, budget digest, `negative_threshold`, and risk-assessment digest. These identities make a receipt attributable to the resources actually used; they do not make the source or target trustworthy.

## 2. Pre-model gates

Three gates run before any model is called, so that a case that cannot be exercised neither consumes a producer session nor is mistaken for a negative:

- `target_binding` resolves the finding's file and target line inside the admitted snapshot.
- `ast_guard` confirms the target line sits inside a callable the recipe can reach and that the recipe's fixed arguments apply to it.
- `build_replay` confirms the snapshot imports and builds inside the pinned image.

A failure at any of these is `UNABLE_TO_RUN`. The gate module is [`src/corsair/policies/verdicts.py`](../../src/corsair/policies/verdicts.py); the admission contracts are in [`src/corsair/contracts/sources.py`](../../src/corsair/contracts/sources.py).

## 3. Producer session

For each permitted session, the workflow creates a fresh producer activity with remaining model/tool budget and the current revision context. The ADK runner receives a bounded packet that excludes private fixtures, oracles, every execution observation, and case paths. The producer may use only `list_files` and `read_file` on the admitted snapshot plus its skills toolset, then returns the native `ProducerDecision` schema: a `Submission` holding the benign and exploit payloads as JSON data, or an explicit abstention.

Native before-model, after-model, and before-tool callbacks account for attempts and enforce episode limits. After ADK returns, Corsair validates the canonical Pydantic model and the round/parent relationship. A no-output, invalid-output, budget, provider, or timeout condition remains typed feedback or an operational result; it is not repaired by a second application-owned parser.

## 4. Differential pair and coverage

Trusted code writes an immutable operation intent binding operation, source, submission, configuration, recipe, image, budget, and fix-revision identities. If a matching completed operation exists, its committed observation is read and revalidated. An intent without a committed observation is uncertain and is not automatically replayed.

For a new operation, the kernel materializes the recipe with the proposed payloads and the Docker adapter runs one fresh container for the control role and one for the exploit role. The two runs share snapshot, image, recipe, fixtures, and fixed arguments; only the payload differs. Each run returns raw receipts and a coverage record, not a conclusion.

`control_coverage` and `exploit_coverage` each require that the finding's **exact target line** executed in that run. A run that never reached the target line observed nothing about it, so the kernel discards the pair as `INCONCLUSIVE` rather than counting it toward any label. This is the primary guard against a false `EXPLOIT_NOT_DEMONSTRATED`.

`evidence_agreement` then checks raw/driver identity, cleanup confirmation, source and submission digests, image identity, and agreement between the native exit status, the test report, and the driver report. Only then is a validated `Observation` committed with the evidence bundle. The verifier is [`src/corsair/steps/verification.py`](../../src/corsair/steps/verification.py).

## 5. Blind audit and fixed differential

`blind_audit` runs a fresh auditor activity. The auditor receives the finding, public recipe configuration, source excerpt, and the proposed pair; it never receives receipts, coverage, or a provisional label. It returns a structured `AuditResult` and can only reject. A rejection removes the pair from consideration; a non-rejection lets the kernel continue. The auditor cannot raise a label.

When the exploit run demonstrated the reported condition with a healthy control and a fix revision was supplied, `fixed_differential` repeats the same pair against that fix revision under its own operation identity. It is optional confirmation, not a precondition for `EXPLOIT_DEMONSTRATED`: a fix revision on which the demonstration no longer occurs confirms the label, while a fix revision on which the exploit still demonstrates (`FixStatus.NOT_BLOCKED`) withholds it as an incomplete fix or a suspect demonstration. When it holds, it says the submitted demonstration was blocked, not that the fix is generally correct.

## 6. Verdict table

The kernel assigns one of six labels; [`src/corsair/contracts/results.py`](../../src/corsair/contracts/results.py) is the schema authority.

| Label | Condition decided in code |
| --- | --- |
| `EXPLOIT_DEMONSTRATED` | Both runs covered the target line, the control held, the exploit run demonstrated the condition, and the auditor did not reject, and the demonstration covers the finding's claimed scope. A supplied fix revision confirms when it blocks the demonstration and withholds the label only when the exploit still demonstrates on it. |
| `COMPONENT_EXPLOIT_DEMONSTRATED` | The same genuine differential (both runs covered the target line, control held, exploit demonstrated, auditor did not reject), but the finding claimed application scope and only the component seam was exercised, so reachability to the claimed application entry point was not established. Developer next step: harden the component or prove an upstream guard blocks the input. |
| `EXPLOIT_NOT_DEMONSTRATED` | At least `negative_threshold` (2) independent producer sessions each produced a coverage-valid, non-rejected pair whose exploit run did not demonstrate the condition. |
| `INCONCLUSIVE` | Gates ran but did not settle a demonstration at any scope: coverage missed in either run, evidence disagreed, the auditor rejected, the exploit still demonstrated on a supplied fix revision, fewer than two independent negative sessions, or the budget ended first. |
| `UNABLE_TO_RUN` | `target_binding`, `ast_guard`, or `build_replay` failed; the case could not be exercised. |
| `ERROR` | An operational failure: provider, sandbox infrastructure, missing artifact, unknown cleanup, or uncertain operation. |

`INCONCLUSIVE`, `UNABLE_TO_RUN`, and `ERROR` are never negative clearance.

## 7. Durable result

Temporal persists workflow coordination and executes activities with a single attempt for model and native side effects; each ADK episode is exactly one activity. The final `record` activity is separately idempotent and retryable, storing a result artifact and immutable operation mapping. Worker/client recovery needs both Temporal history and the shared artifact root.

This is episode-level durability, not turn-level checkpointing inside a model call. [ADR 0001](decisions/0001-sdk-owned-durable-rounds.md) explains that tradeoff; [ADR 0003](decisions/0003-immutable-native-evidence.md) explains the evidence/reconciliation choice; [ADR 0004](decisions/0004-payload-pair-and-coverage-gated-verdict.md) explains the payload pair, coverage gate, and label set.
