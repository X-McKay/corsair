# Intake JSON robustness implementation plan

Status: authorized by the user's request to add varied JSON tests and improve robustness, 2026-10-28. Continue inline within the existing intake design; preserve unrelated dirty changes.

## Design and boundary

Add a separate authored candidate cohort with equivalent reports in different JSON structures and explicit ambiguous/adversarial controls. Keep the original eight cases, source hashes and labels unchanged. Use the existing bounded native ADK episode, canonical contracts, read-only Docker inspection and available-image policy. No new provider, language, image, runtime permission, repair loop or recipe gate.

Approach: combine deterministic parser/admission boundary tests with live fixture evaluation. Parser-only testing cannot measure model normalization; model-only testing cannot establish hard admission limits. Extend evaluator-only oracles with optional exact supplied titles and required description fragments, so a correct classification cannot conceal loss of report details. These assertions are lexical diagnostics, not semantic equivalence. Keep all labels outside model/tool/workflow packets.

## Work

- [x] Add failing scorer regressions for omitted report details and incorrect normalized titles, then implement optional evaluator-only checks without changing legacy scores.
- [x] Freeze 32 cases covering canonical, GitHub, Jira, rich-text, SARIF, nested envelopes, arrays, key/value records, strings, Unicode, noisy metadata, repeated/contradictory findings, missing reports and absent images. Scanner-specific cases cover Semgrep, Bandit, GitLab SAST, Checkov, Trivy dependency reports, empty results and multi-result SARIF; these are illustrative synthetic excerpts with synthetic identifiers, not genuine scanner exports or version-complete schema conformance. Keep source family and input format visible in reports; no aggregate can hide per-format failures.
- [x] Add deterministic JSON type/encoding/size/depth/container/duplicate-key tests. Verify native ADK receives raw noncanonical JSON without rewriting or interpreting metadata as permissions.
- [x] Run the expanded cohort twice at the already configured endpoint before changing runtime instructions. Retain failures and all denominators. Fix only measured, bounded defects, then repeat affected frozen cohorts under a distinct identity if runtime changes are necessary.
- [x] Fresh scoped review; required quality/offline/native checks; build and inspect wheel/resources outside checkout.
- [x] Record actual results and limitations. These related synthetic variants are not independent held-out families or a robustness guarantee; no baseline promotion or publication.

## Review focus

An unavailable image embedded in JSON cannot replace inventory; multiple distinct reports cannot silently become one; repeated equivalent reports need not be multiple issues; missing report text cannot be reconstructed from source; correct decisions with lost normalization facts must fail the new checks. Malformed/oversized inputs fail admission rather than becoming model calls. Model failures remain failures.

## User clarification and test construction

The user clarified that inputs come from diverse InfoSec scanners. Before the first live run, the draft cohort expanded from 24 to 32 cases and added configuration/dependency content alongside the equivalent function reports. The original eight-case dataset and fixtures were not edited. Scanner field shapes were checked against primary documentation: [Semgrep schema](https://github.com/semgrep/semgrep-interfaces/blob/main/semgrep_output_v1.jsonschema), [Bandit JSON](https://bandit.readthedocs.io/en/latest/formatters/json.html), [GitLab scanner integration](https://docs.gitlab.com/development/integrations/secure/), [Trivy reporting](https://www.trivy.dev/docs/latest/guide/configuration/reporting/), [Checkov results](https://www.checkov.io/2.Basics/Reviewing%20Scan%20Results.html), and [SARIF 2.1.0](https://docs.oasis-open.org/sarif/sarif/v2.1.0/os/sarif-v2.1.0-os.html). No scanners or target dependencies are installed or executed.

The new normalization regression failed first because oracle fields were not accepted, then passed after adding evaluator-only checks. All 47 affected parser, evaluator and native-scripted ADK tests passed. Admission tests cover JSON root types, Unicode byte limits, container/depth boundaries, duplicate keys, non-finite numbers, malformed JSON and raw packet preservation. Metadata cannot alter actual image inventory or source admission.

Initial live diagnostic: `.venv/bin/python -m corsair.evaluation.intake evals/datasets/intake-json.json --settings .state/intake-json-20261028/settings.json --repeats 2 --seconds 60 --output .runs/intake-json-20261028/before.json`, using the same configured model/provider and runtime prompt as PLAN-0134. The separate private settings change only artifact-root location. Keep all 64 planned attempts and subsequent variants distinct.


## Preserved setup failure and reviewed revision

The first 64-attempt sweep completed with 64 source-admission operational failures before any model call. The initial fixture used `../repository`; the unchanged normalized-path/no-follow admission correctly rejected that spelling. The prior test verified a shared source directly but missed each request's actual path. The regression now admits the exact path constructed by the evaluator and was observed failing before correction. Revision 1's manifest and all fixture/source bytes are retained privately in `.work/intake-json-20261028/cohort-v1`, with its complete report `.runs/intake-json-20261028/before.json`.

Frozen revision 2 gives every case an ordinary `repository` directory with the same source digest, without resolving away parent traversal or relaxing runtime admission. Review also identified an over-strict ambiguous-report oracle. Revision 2 explicitly permits the grounded shared path for the multiple/conflicting controls while requiring `needs_input`; optional evaluator-only `permitted_paths` preserves legacy exact path semantics by default. Regression coverage accepts retained or withheld shared paths and rejects invented paths. Report rows now retain source family and input-format metadata, outside the agent packet. All 48 affected tests passed after these corrections.

The first offline suite passed **346 tests, 81 deselected**, 11.95s. It preceded the added admission-path/optional-path regressions. One subsequent quality run caught formatting in the new regression; the affected file was formatted with pinned Ruff. A final quality/offline sweep remains required.

Revision-2 initial diagnostic uses the same command with output `.runs/intake-json-20261028/baseline-v2.json`, two repeats, 60-second episodes and unchanged runtime instructions. The complete revision-1 failure denominator remains separate, not reclassified as successful model attempts.


## Measured runtime failure classes and bounded candidate

The revision-2 first pass exposed valid normalized issues with empty top-level grounding; silent first-finding selection in multiple/contradictory reports; image withholding under misleading metadata; and scan-status/vague-title content treated as an issue. Surface and language labels also slipped. These are genuine model errors, not malformed JSON: the partial run had no schema-invalid output.

A prompt-only candidate was drafted privately while the baseline resources remained unchanged. It distinguishes finding records from scan/tool/log metadata; deduplicates only equivalent claims and boundaries; requires explicit missing-input/multiple-issue categories; treats payload image names as report data; maps scanner paths only to unambiguously inspected relative paths; and requires top-level grounding separately from nested reported locations. It does not introduce a scanner parser registry, fixed recipe or extra inference loop. Reviewer caught an absolute-path wording conflict; that was corrected before use. Both nested and top-level canonical Location fields retain safe relative-path validation.

Reviewed fixture/oracle corrections have no remaining important findings. Final pre-prompt offline suite: **347 passed, 81 deselected**, 11.60s. Intake native Docker/Temporal checks: **4 passed, 1 live test deselected**, 19.18s. Pinned lint/format/ty/docs checks passed. Live diagnostic remains independent from those native checks and hypothetical inventories do not prove physical image admission.


## Completed baseline and final candidate

The completed revision-2 baseline retained all **64/64 attempts**: **38/64 exact**, **48/64 correct decisions**, **4 false-supported**, **0 invalid outputs**, **3 model failures**. Repeat exact scores were 20/32 and 18/32; both had 24/32 correct decisions. Detail-preservation checks passed on 44 returned proposals; 48 attempts had such expectations, with three model failures and one lexical mismatch. This is 44/48 against the planned relevant denominator, not 44/45 conditioned on valid output. Runtime identity remained `4623709f565e67b469c0926827c3b5567f0450d3f97e501232a0f7f15883c3d2` throughout.

Only after completion was the reviewed prompt installed. The canonical schema, provider/model, budgets, scorer and revision-2 fixture/oracle bytes remain unchanged. One sequential final process first evaluates the original eight-case cohort once, then revision 2 twice; reports are `.runs/intake-json-20261028/original.json` and `candidate-v2.json`. Equivalent public entry points are `python -m corsair.evaluation.intake DATASET --settings .state/intake-json-20261028/settings.json --repeats N --seconds 60 --output PATH` with N=1 and 2 respectively. No live requests compete with one another.

Final guidance review found no remaining important conflicts after the relative-path correction. It remains a consistency review, not model qualification. Additional UTF-8/BOM/UTF-16 and CRLF cases brought affected unit/native-scripted checks to **51 passing tests**. Final full native, quality, build and live outcomes follow below once completed.

## Completed prompt-only boundary and continuation

Final prompt-only scanner result: **39/64 exact, 52/64 correct decisions, two false-supported, zero invalid outputs, three model failures**. The original eight-case repeat had **6/8 exact and 8/8 correct decisions**, without invalid outputs/model failures. This is a small exact-match change, not a robustness qualification. All reports are complete and the evaluator verified unchanged input/source/inventory/settings digests and episode ceilings between revision-2 baseline and candidate. [Per-format results](../../../evals/experiments/2026-10-28-intake-json.md) retain every mismatch. Final offline/native gates were **350 passed, 81 deselected** and **11 passed, one live test deselected**; quality, installed-wheel loading outside checkout and package checks passed with the existing uv version-range build warning.

The user's subsequent request for an agentic image tool/skill is implemented and separately measured in [PLAN-0136](PLAN-0136-intake-image-tool.md). The requested workflow connection follows under [PLAN-0137](PLAN-0137-intake-investigation-handoff.md); remaining model false-supported examples cannot be erased by workflow wiring. No fixture/oracle was relabelled after its frozen revision; the first setup failure remains archived separately.
