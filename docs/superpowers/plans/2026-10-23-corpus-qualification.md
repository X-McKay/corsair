# Licensed Multilingual Corpus Qualification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the four-case synthetic release set with a schema-validated, rights-reviewed corpus of 44 paired vulnerability families: four conformance families plus ten real upstream families in each of Python, JavaScript, Java and Perl, while keeping unqualified historical material out of every score.

**Architecture:** Evaluator-only Pydantic models load a versioned manifest under `benchmarks/dataset/`; agent-visible `input.json` remains the small `corsair-lite/1` request. Cases acquire exact upstream commits by HTTPS Git, keep truth and rights outside model context, and enter a scored split only after three fresh reference replays plus independent review. The first five cross-language batches establish a 24-family phase-one baseline; five further batches pass the same admission path before the 44-family development corpus is frozen.

**Tech Stack:** Python 3.12, Pydantic, pytest, Git, existing Docker adapters for Python/Node/Java/Perl.

**Spec:** `docs/superpowers/specs/2026-10-23-multilingual-benchmark-and-improvement-loop-design.md`

## Global Constraints

- Implement after `2026-10-23-probe-verdict-contract.md` and `2026-10-23-multilingual-script-coverage.md`.
- One scored sample is one vulnerability/fix family; aliases, backports and execution variants never increase the independent-family denominator.
- Oracle, split, rights, review and expected-result data must never enter `Case`, prompts, producer tools, auditor input or mounted source trees.
- Public cases use pinned upstream acquisition recipes by default. Do not vendor source, tests or PoCs unless redistribution rights and notices are reviewed for the exact files.
- A repository being public is not license evidence. Missing, conflicting, noncommercial or `NOASSERTION` material stays in quarantine.
- Do not copy advisory prose or upstream tests into a finding or probe. Write sanitized findings and reference probes independently; retain only attributed identifiers and links unless their exact terms permit more.
- Resolve every tag, first-parent expression and branch to a full 40-character commit before adding a case.
- Admission requires all four role/revision executions, exact target coverage, three consecutive fresh-container replays and independent technical review.
- The repository owner must approve the license for Corsair-authored benchmark metadata, probes and fixtures before Task 4. Proposed simple default: Apache-2.0 for all Corsair-authored benchmark material. This does not relicense upstream source or advisory text.
- Run `make corpus-check` after every manifest change and `make benchmark-verify EVAL_SET=<affected-set> ATTEMPTS=3` before admission.
- The 24-family point is a phase-one baseline, not development completion. Completion requires 40 qualified real upstream families, exactly ten per language, plus four conformance families; backlog rows, variants, aliases and private regression cases never satisfy that count.
- Vulnerability-type and package/framework strata become release gates only at five independently qualified families. Smaller strata remain visible with exact counts and are informational; never broaden a taxonomy after seeing results to manufacture the threshold.

## Review Focus

- Adding `expected_label` to `input.json` or any `Case` serialization must fail `test_oracle_fields_never_cross_agent_boundary` in Task 1.
- Two cases sharing an alias, patch hash or vulnerable/fixed commit pair across splits must fail `test_family_leakage_is_rejected` in Task 2.
- A rights record that cites only a default-branch license must fail `test_rights_require_revision_and_evidence_hash` in Task 2.
- A reference replay with one missing target line must leave the case `candidate`; pin this in `test_admission_requires_three_complete_replays` in Task 3.
- Variants must contribute one family-weighted point; pin direct/script clustering in `test_variants_share_one_family` in Task 4.
- Backlog, private regression and conformance-variant rows must not satisfy the ten-real-families-per-language target; pin this in Task 10 and the final inventory test in Task 15.
- Package/framework strata with fewer than five independent families must remain informational; pin the exact numerator/denominator inventory in Task 15 and the release-gate boundary in the metrics plan.
- A failed dependency or historical-runtime spike is a qualification failure, never evidence for either security disposition.

---

### Task 1: Define evaluator-only dataset models and boundaries

**Files:**
- Create: `src/corsair/corpus.py`
- Create: `benchmarks/dataset/manifest.json`
- Create: `benchmarks/dataset/README.md`
- Create: `tests/test_corpus.py`
- Modify: `src/corsair/case.py`

**Interfaces:**
- Produces: `DatasetManifest`, `DatasetCase`, `RightsRecord`, `ReviewReceipt`, `ReplayReceipt`, `load_manifest(path)`, and `select_cases(manifest, eval_set)`.
- Preserves: `Case` and `_Request` without oracle, split, rights or expectation fields.

- [ ] **Step 1: Write strict schema and boundary tests**

Test unknown fields, duplicate case IDs, duplicate family IDs where not declared as variants, invalid commit/hash formats, invalid split/status pairs and evaluator fields passed to `_Request`. Add `test_oracle_fields_never_cross_agent_boundary` and inspect the complete producer and auditor payloads.

- [ ] **Step 2: Verify the tests fail**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_corpus.py tests/test_contracts.py -v`

Expected: FAIL because the corpus models and manifest do not exist.

- [ ] **Step 3: Implement the strict models**

Use frozen Pydantic models with `extra="forbid"`. The manifest must record dataset/schema versions, opaque case and family IDs, split, qualification status, language, runtime, package/framework, execution mode, vulnerability/CWE/capability/risk tags, aliases, exact source pairs and hashes, target identity, expected per-revision disposition and fix, allowed reason-coded variation, artifact hashes, visibility/retention, rights records and receipt paths.

- [ ] **Step 4: Add a minimal empty manifest and boundary documentation**

Start with no scored cases. Document that `manifest.json`, `oracle.json`, receipts and reference submissions are evaluator-only and never mounted or serialized to agents.

- [ ] **Step 5: Verify and commit**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_corpus.py tests/test_contracts.py -v`

```bash
git add src/corsair/corpus.py src/corsair/case.py benchmarks/dataset tests/test_corpus.py tests/test_contracts.py
git commit -m "feat: define evaluator-only corpus manifest"
```

### Task 2: Validate provenance, rights, hashes and split isolation

**Files:**
- Modify: `src/corsair/corpus.py`
- Create: `benchmarks/dataset/quarantine.json`
- Create: `tests/fixtures/corpus/`
- Modify: `tests/test_corpus.py`
- Modify: `Makefile`

**Interfaces:**
- Produces: `validate_corpus(root) -> CorpusReport` and `make corpus-check`.
- The check is offline after exact source trees have been acquired; it never silently refreshes a branch or tag.

- [ ] **Step 1: Write failing provenance and leakage tests**

Add `test_rights_require_revision_and_evidence_hash`, `test_family_leakage_is_rejected`, `test_source_and_patch_hashes_are_verified`, `test_noassertion_cannot_be_scored`, `test_case_names_do_not_encode_answers`, and `test_quarantine_is_never_selected`.

- [ ] **Step 2: Implement deterministic validation**

Validate every source, annotation, advisory, probe/harness and dependency/image rights layer independently. Require license expression, immutable evidence URL/revision, evidence-file SHA-256, notice obligations, redistribution mode and reviewer. Cluster on aliases, repository/commit pair, affected-region hash and patch hash; emit a review-required warning for high source similarity that cannot be decided mechanically.

- [ ] **Step 3: Quarantine historical material without rewriting it**

List `evals/e2e`, `benchmarks/corpus/infosec-harness` and any stale polarity/oracle cases with exact reason codes. The validator must prove that no quarantine entry enters conformance, development, regression or release selection.

- [ ] **Step 4: Add the Make entry point**

`make corpus-check` runs without a provider, prints a concise error ledger and exits nonzero on schema, rights, hash, split, receipt or boundary failures.

- [ ] **Step 5: Verify and commit**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache make corpus-check`

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache make test-offline`

```bash
git add src/corsair/corpus.py benchmarks/dataset tests/fixtures/corpus tests/test_corpus.py Makefile
git commit -m "feat: fail closed on unqualified benchmark data"
```

### Task 3: Implement immutable qualification receipts and reference replay

**Files:**
- Create: `src/corsair/benchmark.py`
- Create: `benchmarks/dataset/receipts/.gitkeep`
- Modify: `src/corsair/cli.py`
- Modify: `tests/test_corpus.py`
- Modify: `tests/test_eval.py`
- Modify: `Makefile`

**Interfaces:**
- Produces: internal `corsair benchmark-verify --eval-set ... --attempts ...`, immutable replay receipts, and `make benchmark-verify EVAL_SET=... ATTEMPTS=...`.
- This is evaluator tooling, not a model-quality run and not the deferred public `improve` command.

- [ ] **Step 1: Write failing admission tests**

Add `test_admission_requires_three_complete_replays`, `test_changed_oracle_invalidates_receipts`, `test_changed_source_or_probe_invalidates_receipts`, and `test_infrastructure_failure_blocks_admission` using a sandbox double.

- [ ] **Step 2: Implement receipt creation and validation**

Each receipt records manifest/case revision, source/oracle/submission/runtime-image/kernel hashes, role evidence, target coverage, cleanup, timestamps and outcome. Write with exclusive creation under `benchmarks/dataset/receipts/<case-revision>/`; never overwrite an existing receipt.

- [ ] **Step 3: Implement qualification rules**

Only three consecutive complete replays plus a separate signed review receipt change `candidate` to `qualified`. Any material hash change creates a new case revision and clears qualification without deleting old evidence.

- [ ] **Step 4: Add CLI and Make wiring**

Select by manifest set rather than shell wildcards. `ATTEMPTS` controls replay count; `RUNS` remains only the artifact directory.

- [ ] **Step 5: Verify and commit**

Run: `UV_CACHE_DIR=/tmp/corsair-uv-cache uv run --locked pytest tests/test_corpus.py tests/test_eval.py -v`

```bash
git add src/corsair/benchmark.py src/corsair/cli.py benchmarks/dataset/receipts tests Makefile
git commit -m "feat: require replay receipts for corpus admission"
```

### Task 4: License and qualify four conformance families

**Files:**
- Create: `benchmarks/dataset/LICENSE-BENCHMARKS`
- Modify: `benchmarks/dataset/manifest.json`
- Move/modify: the four direct fixtures to `cases/cs-0001-a/` through `cases/cs-0004-a/`
- Modify: the four script fixtures at `cases/cs-0001-b/` through `cases/cs-0004-b/`
- Modify: `tests/test_corpus.py`

**Interfaces:**
- Consumes: the direct conformance fixtures and script variants from the first two implementation plans.
- Produces: four qualified conformance families, one per language, with direct/script variants clustered under the same family.

- [ ] **Step 1: Record the approved Corsair benchmark license**

Add the exact owner-approved license text and rights records covering Corsair-authored fixture source, findings, probes, harnesses and annotations. Keep upstream dependency/image rights separate.

- [ ] **Step 2: Replace answer-bearing paths and document authorship**

Use opaque stable case IDs `cs-0001-a` through `cs-0004-b` and family IDs `cf-0001` through `cf-0004`. Record original authorship, file hashes and creation review. Do not preserve old directory names in model-visible case IDs.

- [ ] **Step 3: Cluster direct and script variants**

Both variants use one family ID per language and one family-weighted scoring unit. Add `test_variants_share_one_family`.

- [ ] **Step 4: Replay and review**

Run: `make benchmark-verify EVAL_SET=conformance ATTEMPTS=3`

Expected: PASS with 4 families, 8 execution variants, exact coverage, 3 receipts per variant and 4 independent review receipts.

- [ ] **Step 5: Commit**

```bash
git add benchmarks/dataset cases tests/test_corpus.py
git commit -m "test: qualify four multilingual conformance families"
```

### Task 5: Qualify real-family batch A

**Cases:** Starlette, cookie, Commons IO, Net::Netmask.

**Files:**
- Create: `cases/cs-1001/`, `cases/cs-1002/`, `cases/cs-1003/`, `cases/cs-1004/`
- Modify: `benchmarks/dataset/manifest.json`
- Create: matching qualification and review receipts under `benchmarks/dataset/receipts/`

- [ ] **Step 1: Resolve exact pairs and historical licenses**

Use Starlette fix `1797de464124b090f10cf570441e8292936d63e3`, cookie `38323bad3aa04bce840103ff6075bc05cc0bf884` to `ab057d6c06b94a7b1e3358e69a685ae49c97b627`, Commons IO fix `2736b6fe0b3fa22ec8e2b4184897ecadb021fc78`, and Net::Netmask fix `9023b403682f1eaadadf6cb71ba0117a1fa4f163`. Resolve any `^` to a full first-parent SHA and hash license/notice files from both revisions. Independently resolve the Commons IO commit's IO-559 title versus the CVE-2021-29425/IO-556 advisory before claiming that alias; keep the case unqualified if the affected-region relationship is not established.

- [ ] **Step 2: Author findings and probes independently**

Exercise `StaticFiles.lookup_path`, `cookie.serialize`, `FilenameUtils` normalization and `Net::Netmask` parsing.
Use exact target lines for the same semantic seam in each revision (`target.lines` for vulnerable and optional
`target.fixed_lines` after line-shifting fixes), and avoid copied upstream regression code.

- [ ] **Step 3: Run build/runtime spikes, then three replays**

Reject rather than patch upstream source if Python 3.12, Node 22, Java 21 or Perl compatibility changes the affected behavior. Record dependency locks and image hashes.

- [ ] **Step 4: Obtain independent technical review and admit the batch**

Run `make corpus-check` and `make benchmark-verify EVAL_SET=development ATTEMPTS=3`; expect 8 qualified families total.

- [ ] **Step 5: Commit**

```bash
git add cases/cs-1001 cases/cs-1002 cases/cs-1003 cases/cs-1004 benchmarks/dataset
git commit -m "test: add first licensed cross-language benchmark batch"
```

### Task 6: Qualify real-family batch B

**Cases:** Jinja, shell-quote, Bouncy Castle, File::Find::Rule.

**Files:**
- Create: `cases/cs-1005/`, `cases/cs-1006/`, `cases/cs-1007/`, `cases/cs-1008/`
- Modify: `benchmarks/dataset/manifest.json`
- Create: matching qualification and review receipts under `benchmarks/dataset/receipts/`

**Interfaces:** Adds four qualified development families without changing the evaluator schema.

- [ ] Resolve and record full vulnerable/fixed pairs around fixes `90457bbf33b8662926ae65cdde4c4c32e756e403`, `6a8a899c62a58a30fb128a7079f02826ed4faee0`, `97578f9b7ed277e6ecb58834e85e3d18385a4219` and `df58128bcee4c1da78c34d7f3fe1357e575ad56f`; preserve exact BSD-3-Clause, MIT, Bouncy Castle MIT-style and Perl-terms evidence. Record Bouncy Castle as a reviewed `LicenseRef` unless rights review explicitly approves a standard SPDX mapping.
- [ ] Create opaque cases `cs-1005`, `cs-1006`, `cs-1007`, `cs-1008` with independently written probes for `do_attr`, shell quoting, BCrypt checking and three-argument-open behavior.
- [ ] Pass rights, source closure, target coverage and three-replay qualification; obtain independent review.
- [ ] Run `make corpus-check` and `make benchmark-verify EVAL_SET=development ATTEMPTS=3`; expect 12 qualified families and no quarantine selection.
- [ ] Commit with `git add cases/cs-1005 cases/cs-1006 cases/cs-1007 cases/cs-1008 benchmarks/dataset`, then `git commit -m "test: add second licensed cross-language benchmark batch"`.

### Task 7: Qualify real-family batch C

**Cases:** Requests, json-schema, jsoup, Module::ScanDeps.

**Files:**
- Create: `cases/cs-1009/`, `cases/cs-1010/`, `cases/cs-1011/`, `cases/cs-1012/`
- Modify: `benchmarks/dataset/manifest.json`
- Create: matching qualification and review receipts under `benchmarks/dataset/receipts/`

**Interfaces:** Adds proxy, prototype, sanitizer and command-injection families through the same dataset contract.

- [ ] Record pairs `302225334678490ec66b3614a9dddb8a02c5f4fe` to `74ea7cf7a6a27a4eeb2ae24e162bcc942a6706d5`, `3b0cec3042a5aac5c967fd43475f5edc4c5b6eff` to `f6f6a3b02d667aa4ba2d5d50cc19208c4462abfa`, the first parent of `4ea768d96b3d232e63edef9594766d44597b3882` to that fix, and the first parent of `30d43e2df13cfca74833b3aa8a641679427c5cd8` to that fix.
- [ ] Create `cs-1009`, `cs-1010`, `cs-1011`, `cs-1012`; explicitly elect the BSD-3-Clause option for json-schema and the reviewed license option for Module::ScanDeps.
- [ ] Validate proxy rebuilding, prototype mutation, URL sanitization and two-argument-open command injection without external network access.
- [ ] Run `make corpus-check` and `make benchmark-verify EVAL_SET=development ATTEMPTS=3`; after independent review, expect 16 qualified families.
- [ ] Commit with `git add cases/cs-1009 cases/cs-1010 cases/cs-1011 cases/cs-1012 benchmarks/dataset`, then `git commit -m "test: add third licensed cross-language benchmark batch"`.

### Task 8: Qualify real-family batch D

**Cases:** PyJWT, EJS, Commons Text, HTML::Scrubber.

**Files:**
- Create: `cases/cs-1013/`, `cases/cs-1014/`, `cases/cs-1015/`, `cases/cs-1016/`
- Modify: `benchmarks/dataset/manifest.json`
- Create: matching qualification and review receipts under `benchmarks/dataset/receipts/`

**Interfaces:** Adds cryptographic, template, interpolation and sanitization families through the same dataset contract.

- [ ] Record pairs `24b29adfebcb4f057a3cef5aaf35653bc0c1c8cc` to `9c528670c455b8d948aff95ed50e22940d1ad3fc`, `80bf3d7dcc20dffa38686a58b4e0ba70d5cac8a1` to `820855ad75034e303be82c482c5eb8c6616da5c5`, the first parent of `b9b40b903e2d1f9935039803c9852439576780ea` to that fix, and the first parent of `e1978cc37867e85c06a84a4651745235010cd6cd` to that fix.
- [ ] Create `cs-1013`, `cs-1014`, `cs-1015`, `cs-1016` with cryptographic key-type, template compiler-option, interpolation/local-file and HTML-comment sanitization invariants.
- [ ] Keep Commons Text's claim scoped to the exercised default lookup and avoid unsupported JDK JavaScript-engine assumptions.
- [ ] Run `make corpus-check` and `make benchmark-verify EVAL_SET=development ATTEMPTS=3`; after independent review, expect 20 qualified families.
- [ ] Commit with `git add cases/cs-1013 cases/cs-1014 cases/cs-1015 cases/cs-1016 benchmarks/dataset`, then `git commit -m "test: add fourth licensed cross-language benchmark batch"`.

### Task 9: Qualify real-family batch E and freeze the phase-one baseline

**Cases:** Flask, node-tar, zt-zip, HTTP::Tiny.

**Files:**
- Create: `cases/cs-1017/`, `cases/cs-1018/`, `cases/cs-1019/`, `cases/cs-1020/`
- Modify: `benchmarks/dataset/manifest.json`
- Modify: `README.md`
- Modify: `docs/readiness.md`

- [ ] **Step 1: Resolve and review exact pairs**

Use Flask fix `70f906c51ce49c485f1d355703e9cc3386b1cc2b`, node-tar `1e33534e1e96ca6385b3a4749876aea2cda61cea` to `3f7b20097e0daba10441507becbf5b87c6b83b8b`, the first parent of zt-zip fix `759b72f33bc8f4d69f84f09fcb7f010ad45d6fff`, and the first parent of HTTP::Tiny fix `d73c7651e82ace02693842df55928b6c3ae7c38d`. Preserve both revision licenses and all dependency notices.

- [ ] **Step 2: Create the four opaque cases**

Exercise Flask session-cookie scoping, node-tar symlink extraction, zt-zip traversal and HTTP header injection. Use only owned temporary files/process-local observations.

- [ ] **Step 3: Pass phase-one admission**

Run: `make corpus-check`

Run: `make benchmark-verify EVAL_SET=release ATTEMPTS=3`

Expected: PASS with exactly 24 independent families, 6 per language, 20 real upstream families, no quarantine entries and no duplicate family weight. This is the phase-one scoring baseline and does not satisfy the final ten-real-families-per-language target.

- [ ] **Step 4: Freeze the phase-one dataset version and publish the inventory**

Set a content-derived phase-one dataset version before model tuning, record language/framework/CWE/execution-mode counts and list qualification limitations without claiming a private holdout. Keep the development-completion milestone open until Task 15.

- [ ] **Step 5: Commit**

```bash
git add cases/cs-1017 cases/cs-1018 cases/cs-1019 cases/cs-1020 benchmarks/dataset README.md docs/readiness.md
git commit -m "test: freeze the 24-family phase-one corpus"
```

### Task 10: Validate the growth intake without weakening qualification

**Files:**
- Create: `benchmarks/dataset/candidate-backlog.json`
- Modify: `benchmarks/dataset/manifest.json`
- Modify: `benchmarks/dataset/README.md`
- Modify: `tests/test_corpus.py`

- [ ] **Step 1: Add a schema-validated growth backlog**

Track five planned candidates per language, their exact-pair readiness, license status, runtime risk and missing evidence. Seed it with Python urllib3/Werkzeug/Django/aiohttp/PyYAML; JavaScript fast-xml-parser/jsonwebtoken/Express/node-fetch/serialize-javascript; Java BeanUtils/SnakeYAML/Commons Compress/Zip4j/HttpClient with Plexus Utils as the reviewed reserve; and Perl Spreadsheet::ParseExcel/HTTP::Daemon/Archive::Zip/Crypt::JWT/Archive::Tar.

- [ ] **Step 2: Require the same admission path for growth cases**

No backlog entry counts toward coverage or accuracy. Promote through Tasks 11–15 only after exact commits, revision-local rights review, independently authored probes, dependency/image closure, three fresh paired replays and independent technical review. A candidate that cannot run unchanged on the pinned runtime remains in backlog or quarantine; do not patch historical source to make it qualify.

- [ ] **Step 3: Add growth-boundary tests**

Add `test_backlog_does_not_satisfy_qualified_growth_target`, `test_development_target_requires_ten_real_families_per_language` and `test_inventory_separates_real_and_conformance_execution_modes`. Retain `test_variants_share_one_family` from Task 4. Report progress toward ten qualified real development families per language without counting translated synthetic cases, private regressions, aliases or extra variants.

- [ ] **Step 4: Verify and commit**

Run: `make corpus-check`

```bash
git add benchmarks/dataset tests/test_corpus.py
git commit -m "docs: track qualified corpus growth by language"
```

### Task 11: Qualify real-family batch F

**Cases:** urllib3, fast-xml-parser, Commons BeanUtils, Spreadsheet::ParseExcel.

**Files:**
- Create: `cases/cs-1021/`, `cases/cs-1022/`, `cases/cs-1023/`, `cases/cs-1024/`
- Modify: `benchmarks/dataset/manifest.json`
- Create: matching qualification and review receipts under `benchmarks/dataset/receipts/`

**Interfaces:** Promotes four backlog entries through the existing rights, replay and review contracts; produces 28 qualified families, 7 per language.

- [ ] **Step 1: Resolve the exact pairs and historical rights**

Use urllib3 `34be4a57e59eb7365bcc37d52e9f8271b5b8d0d3` to `accff72ecc2f6cf5a76d9570198a93ac7c90270e`, fast-xml-parser `7a7dbac2d0ccf3b7176f38b2ae91600e3c5db0bd` to `2b032a4f799c63d83991e4f992f1c68e4dd05804`, BeanUtils `a83c1eae04c9c99360c3ba4e6a46fd89dc5407ef` to `62e82ad92cf4818709d6044aaf257b73d42659a4`, and Spreadsheet::ParseExcel `19ce0f7a8c989b4bf8163f4b8ffa0ed8bf90cfc5` to `bd3159277e745468e2c553417b35d5d7dc7405bc`. Reacquire and hash the MIT, Apache-2.0/NOTICE and revision-local Perl-5-terms evidence; research memo hashes are discovery evidence only.

- [ ] **Step 2: Author and spike the four independent probes**

Exercise proxy-header removal, XML prototype safety, suppressed `class` introspection and `ExcelFmt` evaluation using owned sentinels. Confirm meaningful common target lines, restore prototype state in `finally`, and reject old-runtime or dependency behavior changes rather than patching source.

- [ ] **Step 3: Replay, review and admit the batch**

Run `make corpus-check` and `make benchmark-verify EVAL_SET=development ATTEMPTS=3`; require independent technical review and expect 28 qualified families with no backlog/quarantine selection.

- [ ] **Step 4: Commit**

```bash
git add cases/cs-1021 cases/cs-1022 cases/cs-1023 cases/cs-1024 benchmarks/dataset
git commit -m "test: add sixth licensed cross-language benchmark batch"
```

### Task 12: Qualify real-family batch G

**Cases:** Werkzeug, jsonwebtoken, SnakeYAML, HTTP::Daemon.

**Files:**
- Create: `cases/cs-1025/`, `cases/cs-1026/`, `cases/cs-1027/`, `cases/cs-1028/`
- Modify: `benchmarks/dataset/manifest.json`
- Create: matching qualification and review receipts under `benchmarks/dataset/receipts/`

**Interfaces:** Adds parser, key-validation, nesting-depth and local-I/O families; produces 32 qualified families, 8 per language.

- [ ] **Step 1: Resolve the exact pairs and historical rights**

Use Werkzeug `7c7ce5cb73f3f7d3b9c09340e4f322aeb583dbc5` to `cf275f42acad1b5950c50ffe8ef58fe62cdce028`, jsonwebtoken `5eaedbf2b01676d952336e73b4d2efba847d2d1b` to `e1fa9dcc12054a8681db4e6373da1b30cf7016e3`, SnakeYAML `4b8d1af4bd422a015fbb07d235f282412c863220` to `fc300780da21f4bb92c148bc90257201220cf174`, and HTTP::Daemon `6bef13437a21a73d06ad713b300a7a184c2bbeec` to `945d35141d94490f749640bd4390acd6a2193995`. Verify both revisions' BSD-3-Clause, MIT, Apache-2.0 and Perl-5-terms evidence plus dependency notices.

- [ ] **Step 2: Author and spike the four independent probes**

Exercise nameless-cookie parsing, asymmetric-key validation, a modest deterministic nesting limit and `send_file` through a socket pair. Generate keys and inputs locally; a timeout, stack exhaustion, launch failure or dependency failure remains nondecisive and blocks qualification.

- [ ] **Step 3: Replay, review and admit the batch**

Run `make corpus-check` and `make benchmark-verify EVAL_SET=development ATTEMPTS=3`; require independent technical review and expect 32 qualified families.

- [ ] **Step 4: Commit**

```bash
git add cases/cs-1025 cases/cs-1026 cases/cs-1027 cases/cs-1028 benchmarks/dataset
git commit -m "test: add seventh licensed cross-language benchmark batch"
```

### Task 13: Qualify real-family batch H

**Cases:** Django, Express, Commons Compress, Archive::Zip.

**Files:**
- Create: `cases/cs-1029/`, `cases/cs-1030/`, `cases/cs-1031/`, `cases/cs-1032/`
- Modify: `benchmarks/dataset/manifest.json`
- Create: matching qualification and review receipts under `benchmarks/dataset/receipts/`

**Interfaces:** Adds ORM, redirect, archive-format and extraction families; produces 36 qualified families, 9 per language.

- [ ] **Step 1: Resolve the exact pairs and historical rights**

Use Django `78e553b48a728ba68b427a8108e1247e5bb46048` to `800828887a0509ad1162d6d407e94d8de7eafc60`, Express `567c9c665d0de4c344b8e160146050770233783c` to `0867302ddbde0e9463d0564fea5861feb708c2dd`, Commons Compress `df7172f4557174da8c06a9acf545f06e8ad0fa2c` to the actual code fix `43354810a9aa4305bf82318f1884e83a078a621a`, and Archive::Zip `5f5219bf030bb2c3dd9734bec69d5fb1beb07cdf` to `5c79b9faae0f1dd67cc8288964c72c12e03884f8`. Do not use Commons Compress documentation-only commit `aae38...`; explicitly review Archive::Zip's revision-local README/Makefile grant rather than substituting a later license file.

- [ ] **Step 2: Resolve the qualification holds and author probes**

Prove Django 4.0 behavior unchanged on Python 3.12, model Express header output through its actual response method, parse an independently generated bounded PAX header, and extract an independently generated ZIP only under an owned root. If a runtime changes the affected behavior or rights remain ambiguous, leave that case unqualified and keep the 36-family milestone open.

- [ ] **Step 3: Replay, review and admit the batch**

Run `make corpus-check` and `make benchmark-verify EVAL_SET=development ATTEMPTS=3`; require independent technical and rights review and expect 36 qualified families.

- [ ] **Step 4: Commit**

```bash
git add cases/cs-1029 cases/cs-1030 cases/cs-1031 cases/cs-1032 benchmarks/dataset
git commit -m "test: add eighth licensed cross-language benchmark batch"
```

### Task 14: Qualify real-family batch I

**Cases:** aiohttp, node-fetch, Zip4j, Crypt::JWT.

**Files:**
- Create: `cases/cs-1033/`, `cases/cs-1034/`, `cases/cs-1035/`, `cases/cs-1036/`
- Modify: `benchmarks/dataset/manifest.json`
- Create: matching qualification and review receipts under `benchmarks/dataset/receipts/`

**Interfaces:** Adds async traversal, redirect disclosure, archive authentication and JWT trust-policy families; produces 40 qualified families, 10 per language.

- [ ] **Step 1: Resolve the exact pairs and historical rights**

Use aiohttp `33ccdfb0a12690af5bb49bda2319ec0907fa7827` to `1c335944d6a8b1298baf179b7c0b3069f10c514b`, node-fetch `f2c3d563755d4d357df987fe871607e296463cef` to `5c32f002fdd65b1c6a8f1e3620210813d45c7e60`, Zip4j `942fe577d6028b1744483beb5eec46699580e5cc` to `597b31afb473a40e8252de5b5def1876bab198d3`, and Crypt::JWT `090535229c562a6b6496922b693b547504683f1d` to `b98a59b42ded9f9e51b2560410106207c2152d6c`. Verify Apache-2.0, MIT and Perl-5-terms evidence at both endpoints.

- [ ] **Step 2: Resolve the runtime and fix-boundary holds**

Use aiohttp's documented pure-Python build without source changes; require deterministic direct request construction or isolated loopback behavior for node-fetch; prove the Zip4j endpoint is complete without follow-up `ddd8fdc8ad0583eb4a6172dc86c72c881485c55b`; and pin CryptX/crypto dependencies for Crypt::JWT. Keep any unresolved candidate out of scored splits.

- [ ] **Step 3: Author probes, replay and review**

Use owned static roots, secret headers, generated/corrupted archives and generated keys. Run `make corpus-check` and `make benchmark-verify EVAL_SET=development ATTEMPTS=3`; require independent review and expect 40 qualified families.

- [ ] **Step 4: Commit**

```bash
git add cases/cs-1033 cases/cs-1034 cases/cs-1035 cases/cs-1036 benchmarks/dataset
git commit -m "test: add ninth licensed cross-language benchmark batch"
```

### Task 15: Qualify real-family batch J and freeze the 44-family development corpus

**Cases:** PyYAML, serialize-javascript, Apache HttpClient, Archive::Tar. Plexus Utils is the reviewed Java reserve.

**Files:**
- Create: `cases/cs-1037/`, `cases/cs-1038/`, `cases/cs-1039/`, `cases/cs-1040/`
- Modify: `benchmarks/dataset/manifest.json`
- Modify: `benchmarks/dataset/README.md`
- Modify: `README.md`
- Modify: `docs/readiness.md`
- Modify: `tests/test_corpus.py`
- Create: matching qualification and review receipts under `benchmarks/dataset/receipts/`

**Interfaces:** Completes and freezes 40 real upstream families plus four conformance families, 11 family-weighted samples per language and at least 48 execution variants.

- [ ] **Step 1: Resolve the exact pairs, rights and final runtime holds**

Use PyYAML `fe150624146ee631bb0f95e45731e8b01281fed6` to `a001f2782501ad2d24986959f0239a354675f9dc`, serialize-javascript `1ac487ed828762eb490ad87022b6b354e0772284` to `f21a6fb3ace2353413761e79717b2d210ba6ccbd`, HttpClient `d9e2140b1260db86f8dc6c77e378733c0459f244` to `08140864e3e4c0994e094c4cf0507932baf6a66a`, and Archive::Tar `621457c3caf84bf15d5d74de33b6de5f13eb0480` to `17c873492a05eddc0de18c1485e0b2cccd5a9158`. If HttpClient cannot preserve the vulnerable behavior unchanged on Java 21, substitute Plexus Utils `f933e5e78dc2637e485447ed821fe14904f110de` to `33a2853df8185b4519b1b8bfae284f03392618ef`, record the substitution and traversal concentration, and keep the same one-family weight.

- [ ] **Step 2: Author and qualify the final four probes**

Use a benign forbidden Python object construction, a deterministic serializer postcondition that does not guess a random UID, an owned certificate/socket or reviewed Plexus archive, and an independently generated TAR link under an owned root. Prove the acquired Archive::Tar tree wins over any base-image core module without clearing adapter instrumentation. Runtime, rights, target-line or determinism failure keeps the final milestone open.

- [ ] **Step 3: Assert the development completion boundary**

Extend the inventory tests to require exactly 44 qualified independent families, 40 real upstream families, 10 real families and 11 total family-weighted samples per language, at least 48 variants, no quarantine/backlog selection and no duplicate alias/commit/region/patch weight. Private regression cases do not satisfy the public-development counts.

- [ ] **Step 4: Replay the release set and freeze a new dataset version**

Run `make corpus-check` and `make benchmark-verify EVAL_SET=release ATTEMPTS=3`. Set a new content-derived development dataset version without overwriting phase-one receipts. Publish exact language, vulnerability-type, package/framework and execution-mode numerators/denominators. A vulnerability-type or package/framework stratum with fewer than five independently qualified families remains informational.

- [ ] **Step 5: Commit**

```bash
git add cases/cs-1037 cases/cs-1038 cases/cs-1039 cases/cs-1040 benchmarks/dataset README.md docs/readiness.md tests/test_corpus.py
git commit -m "test: freeze the 44-family multilingual corpus"
```
