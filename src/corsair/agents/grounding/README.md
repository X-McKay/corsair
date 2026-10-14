# Grounding agent (placeholder)

Grounding reports what human reviewers already concluded about issues like the one under triage. It is
advisory: it does not assess the finding, has no repository access, and nothing downstream reads its output.
The chain records the brief beside the verdict for a person to read. In production it is the Azure DevOps
issue-intake and security-graph grounding agent used in another repository.

**Spec.** "InfoSec Harness: ADO Intake, Security Graph and Grounding Agent (placeholder spec)", Al McKay,
Oct 14 2026. It is not in this repository yet; the lead holds it at `.runs/v2-design/grounding-agent.pdf` with a
text extraction beside it (`grounding-agent.txt`).
TODO(grounding): commit the spec under `docs/` and link it here, replacing this pointer.

## What is here

| Module | Real or stub |
| --- | --- |
| `contracts.py` | Real: `FindingInput`, `Skip`, `ScanRef`, `GraphIssue`, `GraphComment`, `RelatedIssue`, `GraphRepoRef`, `GroundingContext` (`.empty`, `degraded`), `GroundingBrief`, `Precedent`, `PriorDisposition` |
| `intake.py` | Real: WIQL shape check, intake cap (`IntakeTooLarge`), `plain_text`, scanner-header parser, `work_item_to_finding` (no repository means `Skip`; only `Commit:` pins a revision; `source_tool` only from a mapped field), `backfill_location_from_graph`. Stub: `FixtureWorkItems` (fetch) and `InMemoryWriteBack` (one comment per work item, off by default) |
| `graph.py` | Real: `GraphClient` Protocol, the parameterised retrieval queries, hop-count range check, terminal-state filter, `MIN_SIMILARITY`, top-k caps, `get_issue`, `issue_comments`, `find_prior_issues`, `related_issues`, `query_text_for`, `gather` (never raises; failures named in `degraded`). Stub: `InMemoryGraph` fixture; `issue_repo_ref` reads the node's own `repo_url` |
| `citations.py` | Real: `validate_citations`, the deterministic check every brief passes |
| `tools.py` | Real: four read-only tools over the retrieved context only, with the 8 / 6 / 600 / 48 000 render caps |
| `agent.py`, `agent.yaml` | Real: the native agent and `ground(finding, context, model)`, which returns `None` on an empty context without calling the model |

## What the full agent still needs

- An ADO adapter implementing `WorkItemSource` and `CommentSink` over the REST API 7.1 (200 ids per GET, `$top`
  = cap + 1, write-back behind `HARNESS_ADO_WRITEBACK_ENABLED` with a Work Items R&W PAT delivered outside argv).
- A security-graph HTTP client implementing `GraphClient` (`GET /graph/node/{id}` with the id path-encoded,
  `POST /graph/search`, `POST /graph/query`), one client per call site with a 30 s timeout, disabled when the
  base URL is empty (never a default URL in code).
- `issue_repo_ref` composed from the Repositories node coordinates in the configured clone scheme.
- Settings wiring (`HARNESS_SECURITY_GRAPH_*`, field map), a CLI (`ado import`, `issues import`), and an eval set
  with a promoted baseline (`evals/release-policy.yaml` is a placeholder).
- The spec's open questions: the second and third structural guarantees of `Ground`, exact tool signatures and
  prompt text, `/graph/search` label values, the full default field map and `plain_text` tag list, `source_mode`
  and `end_line`/`symbol` types, and a shared batch-report format.
