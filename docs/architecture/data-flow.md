# Data flow

An investigation turns an operator-admitted request into a bounded sequence of payload proposals, differential runs, coverage checks, blind reviews, and an immutable labelled result. Models propose a payload pair and may reject one; they cannot run code, see an outcome, or turn an observation into a label. The kernel gates below run in a fixed order, and each gate that fails stops the investigation at its own label.

```text
request + settings
      │
      ▼
prepare ──► manifest + immutable admitted source snapshot
      │       (request load already bound finding.file to the recipe's module)
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

The request identifies the recipe, the finding (file and, when known, the exact target line), a bounded budget, the source to admit, and an optional fix revision. `prepare` resolves the configured immutable image identity, then admits the source through the local snapshot adapter. Admission uses descriptor/no-follow checks, rejects unsafe/sensitive entries, produces deterministic bounded archive bytes, and can enforce an expected digest. The resulting `PreparedCase` refers to an artifact rather than a live checkout path.

A `RunManifest` records request/configuration identity, image ID, model names, prompt and agent-spec digests, output-schema digests, budget digest, risk-assessment digest, and the admitted `negative_threshold` and `max_sessions` as readable fields. These identities make a receipt attributable to the resources actually used; they do not make the source or target trustworthy.

A request may also originate from an upstream security scanner. The intake mapping in [`src/corsair/entrypoints/requests.py`](../../src/corsair/entrypoints/requests.py) reads a `ScanReport` ([`src/corsair/contracts/intake.py`](../../src/corsair/contracts/intake.py)) and maps one scanner finding onto an internal `Finding`. The scanner's severity, confidence, category and narrative are untrusted self-assessment: they are carried on the finding as a `ScannerClaim` for reporting only and are never read by the verdict kernel, nor placed in any producer or auditor prompt. A scanner finding's claimed scope maps conservatively to `application`, so a genuine demonstration against the supplied repositories is capped at `COMPONENT_EXPLOIT_DEMONSTRATED`: the supplied repositories bound what can be demonstrated, and driving a real application entry point needs an application-entry recipe mechanism that is a known follow-up. A finding whose file is absent from the admitted source cannot bind its target line and resolves `UNABLE_TO_RUN`, never a demonstration or a clean negative. A finding with no line is bound at `prepare`, in trusted code, to the first executable body statement of the recipe function when that function is one plain top-level `def`, and the `PreparedCase` records `line_provenance: recipe_function`; the description is never read for a line or a name (see the [integration guide](../guides/integration.md#admit-a-scanner-finding)).

## 2. Request binding and admission

The Python-only pilot recipe has no build step. Three checks stand between a request and a producer session:

- At request load, a `Case` validator requires `finding.file == recipe.module_file`, so a finding that does not bind to its recipe's module is rejected before any work is spent. The admission contracts are in [`src/corsair/contracts/sources.py`](../../src/corsair/contracts/sources.py).
- Admission snapshots the source into an immutable artifact, so every later run reads the same bytes.
- The pre-model `target_binding` gate ([`src/corsair/policies/target_binding.py`](../../src/corsair/policies/target_binding.py)) reads the admitted recipe module and, with `ast`, blocks the case as a non-retryable `PREPARE_BLOCKED` (`UNABLE_TO_RUN`, with the typed reason) when the finding declares no line and none could be derived from the recipe function (`derive_target_line` in the same module, which `prepare` applies first), the line is beyond the module, the module does not parse, the recipe function is not bound anywhere in the module or is a coroutine function, or, for one plain top-level `def`, `payload_parameter` or a `fixed_kwargs` key is not a keyword parameter (without `**kwargs`) or a required parameter is never supplied. It blocks only a certain violation: a decorated, conditionally defined, re-bound, imported or star-imported callable passes to the run-time gates. It does not require the line to lie inside the callable, since a target may sit in a helper or at module level, and it checks the vulnerable revision only.
- Line binding ([`src/corsair/policies/line_binding.py`](../../src/corsair/policies/line_binding.py)) then chooses, in code, the exact line the coverage gate will require: the line coverage.py reports for the declared one. A function's `def`, decorator, signature-continuation or docstring line binds to the first statement of its body (skipping the docstring and `global`/`nonlocal`), so the gate asks that the function was entered rather than merely defined at import. Any other continuation line of a multi-line logical line (statement, compound header, `except`/`case` clause, decorator, or `;`-joined statements) binds to that logical line's first line. A line `derive_target_line` derived for a line-less finding is already a body statement that starts its own line, so it passes through unchanged. Every other line, including a declared line that already starts a statement, a module or class docstring, a comment or blank line between statements and the `else:`/`finally:` lines, is kept. The declared (or derived) line stays in `PreparedCase.finding.line` with its `line_provenance`; the bound line is recorded as `PreparedCase.target_line`, and `inspect --evidence` reports the bound line as `target_line` beside `declared_line` and `line_provenance`. A record made before line binding has no `target_line`, and the kernel then binds to the declared line.

The verdict-time gates still bind the target line: a finding with no declared line is `UNABLE_TO_RUN`, and a declared line that does not execute in both runs is `INCONCLUSIVE` (see §4 and §6). The pre-model gate removes the producer session an absent, out-of-range or unbindable target used to cost; it never stands in for coverage. The policy module is [`src/corsair/policies/verdicts.py`](../../src/corsair/policies/verdicts.py).

## 3. Producer session

For each permitted session, the workflow creates a fresh producer activity with remaining model/tool budget and the current revision context. The ADK runner receives a bounded packet that excludes private fixtures, oracles, every execution observation, and case paths. The producer may use only `list_files` and `read_file` on the admitted snapshot plus its skills toolset, then returns the native `ProducerDecision` schema: a `Submission` holding the benign and exploit payloads as JSON data, or an explicit abstention.

Native before-model, after-model, and before-tool callbacks account for attempts and enforce episode limits. After ADK returns, Corsair validates the canonical Pydantic model and the round/parent relationship. A no-output, invalid-output, budget, provider, or timeout condition remains typed feedback or an operational result; it is not repaired by a second application-owned parser.

## 4. Differential pair and coverage

Trusted code writes an immutable operation intent binding operation, source, submission, configuration, recipe, image, budget, and fix-revision identities. If a matching completed operation exists, its committed observation is read and revalidated. An intent without a committed observation is uncertain and is not automatically replayed.

For a new operation, the kernel materializes the recipe with the proposed payloads and the Docker adapter runs one fresh container for the control role and one for the exploit role. The two runs share snapshot, image, recipe, fixtures, and fixed arguments; only the payload differs. Each run returns raw receipts and a coverage record, not a conclusion.

`control_coverage` and `exploit_coverage` each require that the finding's **exact target line** (the declared line as bound at prepare, `PreparedCase.bound_line`) executed in that run. A run that never reached the target line observed nothing about it, so the kernel discards the pair as `INCONCLUSIVE` rather than counting it toward any label. This is the primary guard against a false `EXPLOIT_NOT_DEMONSTRATED`.

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
| `UNABLE_TO_RUN` | The case could not be exercised against a bound target: the finding declared no target line and none could be derived from the recipe function, the pre-model `target_binding` gate found the line or recipe callable certainly unbindable, or a source-admission or sandbox-availability gate blocked before any evidence ran. (The no-target-line check runs both before the model, in `target_binding`, and at verdict time.) |
| `ERROR` | An operational failure: provider, sandbox infrastructure, missing artifact, unknown cleanup, or uncertain operation. |

`INCONCLUSIVE`, `UNABLE_TO_RUN`, and `ERROR` are never negative clearance.

## 7. Durable result

Temporal persists workflow coordination and executes activities with a single attempt for model and native side effects; each ADK episode is exactly one activity. The final `record` activity is separately idempotent and retryable, storing a result artifact and immutable operation mapping. Worker/client recovery needs both Temporal history and the shared artifact root.

This is episode-level durability, not turn-level checkpointing inside a model call. [ADR 0001](decisions/0001-sdk-owned-durable-rounds.md) explains that tradeoff; [ADR 0003](decisions/0003-immutable-native-evidence.md) explains the evidence/reconciliation choice; [ADR 0004](decisions/0004-payload-pair-and-coverage-gated-verdict.md) explains the payload pair, coverage gate, and label set.
