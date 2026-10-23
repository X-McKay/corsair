# Multilingual benchmark and improvement-loop design

**Date:** 2026-10-23

**Status:** Architecture approved in discussion; written specification awaiting review

**Baseline:** `improve/duo-playbook` at `ae4b5f23`

**Evaluation method:** X-McKay playbooks `build-agent-evals`

## Purpose

Corsair needs a defensible evaluation program for Python, JavaScript, Java and Perl. It must exercise real vulnerable
and remediated code, support library calls and repository-local script entrypoints, distinguish positive evidence from
honest non-confirmation, and expose where model, language, framework and vulnerability-class performance differs.

This design changes the probe result contract, adds a scoped negative disposition, creates a licensed and
schema-validated benchmark corpus, records quality/cost/latency evidence, and adds a developer skill for turning
reviewed Azure DevOps remediation failures into durable regression cases.

The design follows these playbook rules:

- deterministic assertions own schemas, exact evidence and security gates;
- hard invariants cannot be averaged into an accuracy score;
- stochastic cases are repeated and retain their model, prompt, skill, policy and dataset versions;
- release evidence reports quality beside latency, tokens and cost;
- reviewed failures are promoted into a versioned regression dataset;
- expected results are never edited merely to make a change pass.

## Goals

1. Standardize one differential-probe contract across Python/pytest, JavaScript/node:test, Java/javac and Perl/TAP.
2. Make the words `PASS` and `FAIL` mean whether each probe achieved its role-specific objective.
3. Emit `LIKELY_EXPLOITABLE` when the control and exploit objectives both pass.
4. Emit a narrowly scoped `LIKELY_NOT_EXPLOITABLE` when the control passes and a valid exploit attempt cleanly fails.
5. Support targets reached by direct calls and by executing repository-local scripts, CLIs or Java main classes.
6. Qualify an initial 24-case, four-language release corpus and grow the public development corpus to at least 40
   independent vulnerability families.
7. Treat vulnerable and fixed revisions as one paired scoring unit and prevent family leakage between splits.
8. Record exact provenance and separate rights for source, annotations, advisory text, probes, harnesses and runtime
   dependencies.
9. Gate releases at 80% first-attempt paired accuracy overall and for each supported language.
10. Track latency, tokens and cost and make controlled comparisons between model configurations straightforward.
11. Report accuracy by language, vulnerability type, framework/package family and execution mode.
12. Provide one developer skill that evaluates closed Azure DevOps issues, guides improvement and promotes failures
    into the regression corpus.

## Non-goals

- This work does not add a public `corsair improve` command.
- It does not add another sandbox, scheduler, workflow engine or retry framework.
- It does not claim that one failed payload proves a package is safe from all possible attacks.
- It does not accept timeouts, incidental exceptions or build failures as evidence that an exploit worked or failed.
- The initial script support does not include remote services, browsers, databases outside the case container or
  timing-only denial-of-service evidence.
- Public cases do not make a credible secret holdout. A future private holdout must be stored and operated separately.
- Historical v2 labels are not migrated by string replacement. Each case must be re-adjudicated.

## Terminology

### Security invariant

`run_target(payload)` returns a Boolean security invariant in every supported language:

- `true`: the security invariant held;
- `false`: the reported security condition occurred.

An exception is not a Boolean result. It is an error observation even if the exception resembles the expected fixed
behavior. A probe may catch a precisely expected application rejection and then return the corresponding invariant,
but broad exception swallowing is invalid.

### Probe roles and role results

One submitted probe defines `CONTROL_PAYLOAD`, `EXPLOIT_PAYLOAD` and `run_target(payload)`. The trusted adapter runs
the unchanged probe twice in separate fresh containers and keeps the role out of submitted code.

| Role | Expected invariant | `PASS` means | `FAIL` means |
| --- | --- | --- | --- |
| control | `true` | expected benign behavior was observed | the reported condition occurred for the control |
| exploit | `false` | exploitability was observed | the invariant held for this exploit attempt |

The complete user-facing role-result vocabulary is `PASS`, `FAIL`, `ERROR`, `NOT_RUN` and `INFRA`. `FAIL` is reserved
for a clean Boolean mismatch. Compilation errors, exceptions, malformed native evidence and missing reports cannot be
collapsed into `FAIL`.

The kernel may retain internal observations such as `holds` and `violated`, but they are not the public probe-result
contract.

### Case dispositions

The public case dispositions are:

- `LIKELY_EXPLOITABLE`
- `LIKELY_NOT_EXPLOITABLE`
- `INCONCLUSIVE`
- `UNABLE_TO_RUN`
- `ERROR`

`LIKELY_NOT_EXPLOITABLE` is scoped to the reported finding, submitted exploit payload, exact source revision and
tested preconditions. It is not a general safety claim.

`LIKELY_EXPLOITABLE` remains the canonical stored positive enum. User-facing prose may explain that the code is
potentially exploitable, but no second `POTENTIALLY_EXPLOITABLE` enum is introduced.

Each evaluated revision receives its own disposition record. The top-level case label mirrors the vulnerable/source
revision for compatibility, while the fixed/remediated revision record and the derived fix status remain separately
available. This makes a remediated `LIKELY_NOT_EXPLOITABLE` or reason-coded `INCONCLUSIVE` observable without
overloading `verified`.

## Probe and execution contract

### One differential probe

The producer supplies one hypothesis, one reproducible build script and one differential probe. The probe has the
same setup, target call and invariant for both payloads. It must not:

- receive the role or expected answer;
- compare the input with `CONTROL_PAYLOAD` or `EXPLOIT_PAYLOAD` to choose an answer;
- replace the affected target with a mock;
- change the security invariant based on the payload;
- rely on state left by the other role's run.

Each revision is evaluated in this order:

1. replay the submitted build in the controlled build environment;
2. run the control as one native test ID in a fresh offline container;
3. run the exploit as one native test ID in a different fresh offline container;
4. normalize native test and coverage evidence;
5. apply deterministic gates;
6. apply the outcome-blind structural audit;
7. derive role results and the case disposition.

The auditor receives the hypothesis, build recipe and probe, never outcomes, coverage, oracle fields or the producer
transcript. It can reject evidence but cannot assign a verdict.

### Direct calls and script entrypoints

`run_target` may invoke the affected code directly or may execute a repository-local script, CLI, packaged entrypoint
or Java main class as a child process. The probe can observe exit status, stdout, stderr and effects contained in its
owned temporary directory.

A nonzero child exit can be part of a security invariant when the probe explicitly interprets it. Failure to start a
child, a timeout, an uncaught exception or malformed output is an error, not vulnerability evidence.

The sandbox is unchanged for child processes: no network during probe execution, a read-only source tree, dropped
capabilities, no new privileges, fixed resource limits and kernel-owned cleanup. Children cannot escape the limits
that apply to the adapter process.

### Child-process coverage

A decisive result requires evidence that the exact reported target line executed in the process that actually ran the
target. Adapter qualification therefore includes coverage collection and path normalization across descendants:

- Python combines coverage.py data from instrumented subprocesses;
- JavaScript inherits V8 coverage configuration and aggregates child-process reports;
- Java attaches the JaCoCo agent to child JVMs and merges execution data;
- Perl runs child interpreters under Devel::Cover-compatible instrumentation and merges coverage databases.

The implementation plan must begin with a small executable spike for each runtime. A runtime is not advertised for
script targets until the spike proves exact target-line attribution, native evidence agreement and fresh-container
isolation. Missing child coverage makes the case `INCONCLUSIVE`.

## Deterministic decision rules

### Decisive prerequisites

Both decisive labels require all of the following:

- the build replay succeeded;
- both role runs produced clean Boolean evidence;
- both runs reached the exact target file and required target lines;
- native test output and the adapter's structured record agree;
- cleanup was confirmed;
- the structural audit accepted the control, exploit, invariant and claimed causal path.

### Per-revision disposition

| Control result | Exploit result | Disposition |
| --- | --- | --- |
| `PASS` | `PASS` | `LIKELY_EXPLOITABLE` |
| `PASS` | `FAIL` | `LIKELY_NOT_EXPLOITABLE` |
| `FAIL` | any result | `INCONCLUSIVE` |
| any result | `ERROR` or `NOT_RUN` | `INCONCLUSIVE` unless the terminal mapping below applies |
| any result | `INFRA` | `ERROR` |

The second row is valid only when exploit `FAIL` means `run_target` cleanly returned `true`. An exploit-side exception,
timeout, missing report, uncovered target or audit rejection cannot emit `LIKELY_NOT_EXPLOITABLE`.

### Terminal mapping

- Source acquisition, dependency resolution, compilation or runtime unavailability: `UNABLE_TO_RUN`.
- Evaluator, container, cleanup or infrastructure failure: `ERROR`.
- Invalid, ambiguous or incomplete submitted evidence after the allowed producer budget: `INCONCLUSIVE`.

Every nondecisive result retains the last gate and a machine-readable reason code.

### Remediated revision and fix status

The identical probe is run against the fixed revision. When the vulnerable revision is `LIKELY_EXPLOITABLE`:

- fixed control `PASS` plus fixed exploit `FAIL`, with decisive prerequisites satisfied, yields fix `verified`;
- any other completed fixed combination yields `not_verified` with the exact reason;
- no fixed revision yields `not_applicable`.

When a target was deliberately removed or made structurally unreachable by remediation, the remediated revision may
correctly produce `INCONCLUSIVE` with a narrow evaluator-owned reason such as `TARGET_REMOVED`. This is an acceptable
benchmark expectation when the oracle documents it, but it does not become fix `verified`: Corsair did not execute
the former target and must retain `not_verified`.

Generic `INCONCLUSIVE`, build failure, signature drift, dependency failure and unrelated source movement are not
accepted substitutes for a secure fixed result.

## Dataset architecture

### Scoring unit and identity

One scored case is one independent vulnerability/fix family. Its vulnerable and fixed revisions are paired evidence,
not separate samples. CVE, GHSA, PYSEC, CPANSA and vendor aliases, backports, forks, repeated payloads and affected
versions remain in the same family cluster.

Case IDs are stable and opaque. IDs, directory names and agent-visible findings must not encode the expected label,
split or vulnerable/fixed answer.

### Evaluator-only manifest

The versioned manifest lives under `benchmarks/dataset/` and remains outside the agent-visible `Case` model. It records:

- dataset and schema version;
- stable case ID and vulnerability-family ID;
- split and qualification status;
- language, runtime, framework/package family and execution mode;
- vulnerability type, CWE and capability/risk tags;
- advisory aliases and independently written finding provenance;
- vulnerable and fixed repository URLs and full commit IDs;
- source tree, affected-file and patch hashes;
- target file, symbol and required lines;
- expected disposition, fix result and allowed reason-coded variation;
- reference-submission hash and replay receipts;
- reviewer and review-date receipts;
- redaction, visibility and retention classification;
- rights records described below.

The existing strict `corsair-lite/1` request stays small: finding, source revision, optional fixed revision and opaque
case ID. Oracle and corpus metadata never enter prompts or producer tool results.

### Case and source layout

Scored cases continue to use:

```text
cases/<opaque-case-id>/
  input.json
  oracle.json
  reference-submission.json
```

Pinned HTTPS Git commits are the default acquisition method. When a minimal source snapshot is required and
redistribution is permitted, it uses:

```text
benchmarks/corpus/upstream/<language>/<family>/
  vulnerable/
  fixed/
  provenance.json
  LICENSE
  NOTICE              # when required
```

Upstream files remain byte-for-byte intact wherever possible. Reductions or compatibility changes must be separated
from upstream code, record before/after hashes and preserve a reviewable transformation. Generated adapters and
Corsair-authored scaffolding are identified as such.

### Rights model

Each case carries independent evidence for:

1. target source, including tests and vendored files;
2. dataset selection and annotations;
3. advisory prose or identifiers;
4. reference probe and harness;
5. dependencies and container-image redistribution.

Each record retains the asserted license expression, evidence URL and immutable revision, evidence-file hash,
copyright/notice requirements, redistribution mode and reviewer. A dataset-level CC license never relicenses captured
upstream code. A public repository without a license is `NOASSERTION`.

The default public distribution contains Corsair-authored metadata, sanitized finding summaries and pinned
acquisition recipes rather than copied third-party source or PoCs. `NOASSERTION`, custom noncommercial terms,
conflicting notices or missing evidence place expressive imported content in quarantine until resolved. Private Azure
DevOps source remains reference-based and access-controlled.

### Splits

- **Conformance:** small authored cases that exercise contract boundaries, every adapter and both execution modes.
- **Development:** public, real-project cases used for iterative quality work.
- **Regression:** reviewed failures from development or authorized private workflows.
- **Quarantine:** unlicensed, missing, incompatible or not-yet-adjudicated historical material; never scored.
- **Holdout:** future private cases excluded from public development and stored separately.

All variants of a vulnerability family stay in one split. Split validation uses repository/commit identity, aliases,
affected-region and patch hashes, then reviewed similarity checks for near duplicates.

### Initial qualification target

Phase one qualifies 24 paired case families: six per language, consisting of one explicitly licensed conformance
anchor and five real upstream vulnerability families. A conformance anchor can contain direct-call and script
variants in the same family so both execution modes are covered without pretending the variants are independent
samples. Existing synthetic anchors count only after their authorship and license evidence are explicit; otherwise
they are replaced with newly authored equivalents.

| Language | Initial real-family candidates | License observed during discovery |
| --- | --- | --- |
| Python | Starlette, Jinja, Requests, PyJWT, Flask | BSD-3-Clause, BSD-3-Clause, Apache-2.0, MIT, BSD-3-Clause |
| JavaScript | cookie, shell-quote, json-schema, EJS, node-tar | MIT, MIT, BSD option from dual terms, Apache-2.0, ISC |
| Java | Commons IO, Bouncy Castle, jsoup, Commons Text, zt-zip | Apache-2.0, upstream MIT-style terms, MIT, Apache-2.0, Apache-2.0 |
| Perl | Net::Netmask, File::Find::Rule, Module::ScanDeps, HTML::Scrubber, HTTP::Tiny | Perl terms, Perl terms, Perl/GPL/Artistic choices, Perl_5, Perl_5 |

Candidates can be replaced when runtime replay, license review or exploit semantics fail, but replacements must retain
language count and improve framework/package and vulnerability-type diversity. Historical `evals/e2e` material and
the `infosec-harness` copy remain quarantined until independently licensed and re-adjudicated.

The license column is discovery evidence, not admission. Intake must read and hash the exact historical license and
notice files and preserve the precise dual-license choices. Java compatibility work must record the historical
toolchain or transparent source-closure decision instead of silently changing upstream source; Node CJS/ESM, Python
package, and Perl core-module shadowing behavior must likewise be proven in their target images.

After phase one, the public development set grows to at least ten independent families per language. No language or
unsupported framework can be padded with translations of another language's synthetic case.

### Admission lifecycle

A case moves from candidate to scored only after:

1. advisory and issue/fix-family identity review;
2. exact vulnerable/fixed commit and source-tree capture;
3. source, annotation, advisory, probe, dependency and redistribution review;
4. an independently authored reference differential probe;
5. exact target-line coverage on both roles and revisions where the target remains present;
6. three consecutive paired replays in fresh offline containers;
7. independent technical review of the finding, invariant, payloads and expected results;
8. schema, hash, split and answer-leakage validation.

Qualification receipts are immutable inputs to later release reports. Changing an oracle, source pair, probe or
material dependency creates a new case revision and repeats admission.

## Validation and evaluation commands

Implementation will expose three repository-level entry points while retaining existing focused commands:

```text
make corpus-check
make benchmark-verify EVAL_SET=conformance|development|regression|release
make eval EVAL_SET=conformance|development|regression|release ATTEMPTS=<n> PROVIDER=<config>
make compare-evals BASELINE_RUN=<run-id> CANDIDATE_RUN=<run-id>
```

`corpus-check` is deterministic and validates schemas, identifiers, source references, hashes, rights evidence,
expectations, split isolation, framework/language coverage, evaluator-only boundaries and review receipts.

`benchmark-verify` executes trusted reference submissions. Admission requires three clean replays. Normal pull
requests can run one conformance replay; corpus, kernel, adapter, image or sandbox changes run the complete affected
development and regression reference set three times.

The `release` set is a manifest-defined union of qualified conformance, development and regression cases. Quarantine
is never included implicitly.

`eval` runs the producer and auditor and writes machine-readable rows plus a human-readable scorecard. It never treats
a scripted model or sandbox double as model-quality evidence.

`compare-evals` is deterministic. It verifies that the two run manifests used comparable dataset, prompt, skill,
tool, image, budget and sampling inputs before reporting overall and stratified differences. The existing `RUNS`
setting remains the artifact-directory path; `ATTEMPTS` is the independent evaluation-repeat count.

## Accuracy and release gates

### Paired first-attempt accuracy

An **attempt** is one fresh end-to-end producer run with its configured request, token, tool and submission budgets.
The producer may correct rejected submissions within that budget. A repeated attempt starts a new producer run with a
fresh workspace and containers. “First attempt” means attempt index one, not the producer's first submitted draft.

The primary release metric is first-attempt paired accuracy. A case receives one correct point only when the same
generated probe produces both expected revision outcomes:

- vulnerable revision: `LIKELY_EXPLOITABLE`;
- remediated revision: `LIKELY_NOT_EXPLOITABLE`, or a specifically oracle-approved `INCONCLUSIVE` reason such as
  `TARGET_REMOVED`.

The derived fix value must also match the oracle: normally `verified` for the decisive secure after-state and
`not_verified` for an accepted removed-target case.

An allowed `TARGET_REMOVED` result counts as correct evaluation behavior but retains fix `not_verified`. Generic
inconclusive results count as incorrect. An infrastructure failure blocks a complete release run rather than being
removed from the denominator.

Repeated attempts report stability and success-within-N but cannot inflate first-attempt accuracy.

### Minimum threshold

A release requires at least 80% first-attempt paired accuracy:

- across the complete release set; and
- independently for Python, JavaScript, Java and Perl.

With small samples, the report shows the numerator, denominator and confidence interval rather than only a
percentage. A language without enough qualified cases blocks the claim that it is supported.

Accuracy is always stratified by vulnerability type/CWE, language, framework/package family and direct-call versus
script execution. A vulnerability-type stratum becomes an additional 80% release gate after it has at least five
independent families; smaller strata remain visible but informational.

Framework/package-family strata always show exact numerators and denominators. A framework-level performance claim
requires at least five independent families; once that threshold exists, the same 80% gate applies.

### Absolute gates

Regardless of mean accuracy, a release fails on:

- a sandbox, authorization, oracle-leakage or evaluator-integrity violation;
- a decisive false-safe result on a known vulnerable revision;
- a decisive false-exploitable result on a known remediated revision;
- a corpus validation or trusted reference replay failure;
- incomplete language coverage or a claimed integration without a qualified case;
- evaluator infrastructure errors that prevent a complete scorecard;
- regression below a stricter frozen threshold recorded in `benchmark-policy.json`.

The first qualified baseline creates `benchmark-policy.json` with the 80% floor, sample sizes, per-language results,
absolute gates and any stricter observed baseline tolerance. It is frozen before prompt, skill or implementation
tuning against the dataset.

## Metrics and model comparison

Every evaluation run produces an immutable manifest and per-attempt rows containing:

- run ID, timestamps and dataset/split identity;
- provider configuration hash and producer/auditor model names;
- sampling parameters and seed when the provider supports one;
- prompt, developer-skill, producer-skill, policy, matrix, image and kernel hashes;
- case/family ID and all stratification fields;
- expected and observed role results, dispositions, fix status, gate and reason;
- request, submission, tool-call and retry counts;
- input, output, cached and reasoning tokens when the provider exposes them;
- provider-reported cost, or an estimate tied to a versioned pricing-table hash;
- acquisition, generation, audit, build, role execution and end-to-end latency;
- artifact hashes and redacted failure summaries.

The scorecard reports first-attempt paired accuracy, success within three attempts, attempt distribution, failure
reasons, p50/p95 latency, token use and cost per attempted and successful case. It reports micro counts and
family-weighted macro summaries so duplicated variants cannot dominate a metric.

Model comparisons reuse the existing validated provider-config shape. Different versioned provider JSON files map
the producer and auditor to named model profiles while credentials remain in environment variables. Comparisons must
hold dataset version, prompts, skills, tools, images, budgets, run count and sampling parameters constant. The eval
report rejects or prominently marks non-comparable runs rather than presenting a misleading delta.

## CI and scheduled evidence

1. Every pull request runs unit tests, offline tests, `corpus-check` and one deterministic conformance replay.
2. Corpus, adapter, image, sandbox or kernel changes run the relevant development/regression reference cases.
3. Prompt or producer/auditor skill changes run three live attempts per public development case when the configured
   provider is available.
4. Scheduled development evaluation runs three attempts per case.
5. A release runs five attempts per future private holdout case while retaining first-attempt accuracy as the gate.

Provider unavailability is reported as blocked evidence, not a passing release and not model error. No live provider
call is required to validate deterministic corpus mechanics.

## Azure DevOps developer skill

### Location and scope

One repository developer skill will live at:

```text
.agents/skills/azure-remediation-eval-loop/SKILL.md
```

It is development guidance and must not be placed in `src/corsair/skills/`, which is agent-visible operator guidance
for probe production. `AGENTS.md` will reference the developer skill and its triggers. The skill will be authored and
tested with the playbook's skill-admission guidance and the `superpowers:writing-skills` workflow.

The skill coordinates existing evaluator functions, Azure DevOps REST/CLI access and small private helper scripts as
needed. It does not add a public Corsair CLI command.

Azure DevOps access is read-only. The skill does not update work items, branches or pull requests.

### Inputs

The normal user input is a list of closed/remediated Azure DevOps work-item IDs. Workspace configuration supplies
organization and project context. Each issue can resolve to a different repository and remediation branch.

Optional per-issue overrides are allowed for ambiguous source mappings, never for expected security outcomes.
Credentials remain environment-owned and are never written to run artifacts.

### Revision resolution

For each issue, the skill:

1. reads the work item and its relation/update history;
2. confirms the issue is closed or explicitly remediated;
3. resolves the originally attached vulnerable commit from immutable development-link history;
4. inspects linked pull requests, commits and branch references to identify that issue's remediation branch;
5. resolves and pins the current branch head at the start of the run;
6. records the branch ref, pinned SHA, relation evidence and resolution method;
7. marks only that issue `NEEDS_MAPPING` when several candidates are equally plausible, then requests one consolidated
   mapping rather than guessing or blocking independent issues.

There is no global remediation-branch assumption. A merged or deleted source branch uses the explicit linked merge
commit or a reviewed mapping; it does not silently fall back to a moving default branch.

### Testing and improvement loop

For every resolved issue, the skill follows:

```text
baseline -> diagnose -> register failure -> change -> focused replay
         -> related-strata replay -> complete regression replay -> compare -> promote
```

The baseline generates one differential probe against the vulnerable commit, requires `LIKELY_EXPLOITABLE`, then runs
the unchanged probe against the pinned remediated commit. The expected after-state is `LIKELY_NOT_EXPLOITABLE` or an
oracle-approved reason-coded `INCONCLUSIVE` such as `TARGET_REMOVED`.

The initial baseline uses one end-to-end attempt per issue so retries cannot hide first-pass behavior. The configured
producer submission budget still applies inside that attempt. Repeated attempts are an explicit later measurement,
not an automatic response to a failed baseline.

The skill records accuracy, latency, tokens, cost, language, framework, execution mode and vulnerability type. It
classifies failure causes before suggesting a change: source mapping, build/runtime, probe contract, target coverage,
audit, disposition kernel, prompt/skill or provider behavior.

The skill guides the smallest justified change, preserves a pre-change run, and refuses to change the oracle to match
new behavior. After a focused pass it reruns related language and vulnerability strata, then the full regression
suite and release gates. A local improvement that degrades another stratum is not accepted.

### Regression promotion

A failed issue is immediately registered as a regression candidate with its expected outcomes fixed from reviewed
source evidence. When a system change corrects the failure, promotion is mandatory before the improvement is
accepted.

Each promoted case has two tracks:

- a deterministic evaluator-only reference probe that guards kernel, adapter, coverage and disposition behavior;
- an end-to-end model case that regenerates a probe from the finding and pinned sources.

Promotion requires provenance and authorization review, source visibility/retention classification, deduplication,
three deterministic reference replays and technical review. Private cases store references, hashes, sanitized
metadata and review receipts without copying proprietary source into the public corpus. Future runs use pinned
vulnerable/remediated SHAs. Refreshing a branch head creates a reviewed case revision rather than mutating prior
evidence.

Private issue IDs and regression metadata live in a configured access-controlled registry or private companion
repository. They are not committed to the public Corsair repository without an explicit publication review. The
public manifest can retain only non-sensitive aggregate coverage when the private registry is unavailable.

## Migration and compatibility

The current repository documents `holds`/`violated`, has no `LIKELY_NOT_EXPLOITABLE`, and treats a fixed exploit that
holds as fix verification. Implementation must update the kernel, all four adapters, drivers, skills, prompts,
contracts, documentation, oracles and tests together. Mixed contracts are forbidden.

Historical v2 cases that mention R4/R5, old polarity or `LIKELY_NOT_EXPLOITABLE` remain quarantined. They become scored
only after their source exists, their rights are known, their invariant is rewritten for the new Boolean contract and
their paired expectations pass current admission.

The migration should keep internal semantic observations where they help evidence normalization, but external JSON,
reports and documentation use the role-relative vocabulary consistently. Any schema/version change must be explicit
and reject stale submissions instead of guessing their polarity.

## Implementation sequence

The implementation plan should preserve these dependency boundaries:

1. Specify schemas and failing contract tests for role results and the negative disposition.
2. Migrate the kernel and four direct-call adapters together.
3. Qualify child-process coverage with one minimal direct/script case per runtime.
4. Add evaluator-only manifest, rights schema, corpus validation and quarantine handling.
5. Admit licensed conformance anchors, then real cases in small cross-language batches.
6. Add immutable run metrics, scorecards, model comparisons and the 80% policy gate.
7. Write and scenario-test the Azure DevOps developer skill.
8. Establish the frozen baseline before tuning prompts or skills on the expanded corpus.

Each step must keep `make test-offline` passing. Kernel, adapter, image or sandbox changes also require `make test`.
Prompt or skill changes require `make eval`; provider unavailability must be recorded as blocked. Corpus/reference
validation must pass before any model-quality claim.

## Acceptance criteria

The design is implemented when:

- all four languages use the same Boolean probe and role-result semantics;
- direct calls and qualified script entrypoints produce exact child target-line evidence;
- both decisive labels require control grounding, exploit evidence and outcome-blind audit acceptance;
- the 24-case first corpus is licensed, schema-valid and passes three reference replays;
- public development growth and quarantine status are visible by language/framework/vulnerability type;
- evaluation reports first-attempt paired accuracy and enforces the 80% overall/per-language gate;
- latency, token and cost p50/p95 values and strata are present in machine and human reports;
- two model configurations can be compared under controlled, hash-verified inputs;
- the Azure DevOps developer skill handles per-issue branches, preserves private-source boundaries and promotes a
  corrected failure into both deterministic and end-to-end regression tracks;
- no old oracle, label or polarity enters a scored run without re-adjudication;
- deterministic tests and required live evidence are reported separately as passed, failed, blocked or unrun.
