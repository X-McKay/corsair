# Evaluator-only benchmark dataset

`manifest.json` is the strict, versioned inventory for qualified benchmark families. It begins empty: a public case
enters a scored split only after its source pair, rights, reference evidence and independent review pass the corpus
qualification workflow.

Every case declares a redaction class: `none`, `metadata_only`, or `source_and_secrets`. This classification is
recorded independently from public/private visibility and retention so reports can enforce the intended disclosure
boundary instead of inferring it from a repository URL.

The manifest, `oracle.json`, qualification/review receipts and reference submissions are evaluator-only. They are
never mounted in producer workspaces, added to `corsair.case.Case`, serialized into producer tools, or included in
the outcome-blind auditor request. Agent-visible `input.json` retains only the `corsair-lite/1` finding and pinned
source revisions. Upstream source is acquired by immutable HTTPS Git commit unless reviewed redistribution rights
explicitly permit a snapshot.

A redistributed local snapshot keeps its upstream repository and vulnerable/fixed commit in `source_pair`. Its
separate `vendored_snapshot` binds the checked-in bytes to the Corsair repository, an ancestor foundation commit,
the exact repository-relative subtree path, and its tree digest. Curators therefore commit source bytes first and
attach the manifest entry in a later commit. Local paths without that binding fail closed; remote `GitSource`
entries cannot carry it.

Vendored target-source rights use the same two-identity rule. The record's `evidence_url`, `evidence_revision`, and
`evidence_sha256` bind a byte-identical copy below `cases/<case-id>/evidence` to an ancestor Corsair commit. Its
nested `origin` records the immutable upstream `url`, `revision`, and `sha256`; the upstream repository and revision
must equal the corresponding `source_pair` revision, and both hashes must agree. Validation reads the Corsair Git
blob and current disk file directly, rejects missing objects, unsafe paths, links, and uncommitted drift, and never
fetches or consults the source cache. Direct `GitSource` rights retain their upstream evidence fields and cannot
carry this local-copy origin binding. Other rights layers retain their existing direct evidence records.

`target.lines` binds the submitted hypothesis and vulnerable revision. When a fix shifts the same semantic seam,
`target.fixed_lines` records its fixed-revision line identity; omitting it keeps the original shared-line behavior.
The fixed mapping stays in this evaluator-only manifest. Corpus region hashes, native coverage, replay receipts,
and admission checks use the line tuple for their own revision.

The `quarantine` split is never scored. A public repository is not license evidence, and missing, conflicting,
noncommercial or `NOASSERTION` material remains quarantined until separately resolved.

## Corsair-authored benchmark license

The unmodified Apache License 2.0 text in `LICENSE-BENCHMARKS` covers the Corsair-authored benchmark material in
`cases/cs-0001-a`, `cases/cs-0001-b`, `cases/cs-0002-a`, `cases/cs-0002-b`, `cases/cs-0003-a`, `cases/cs-0003-b`,
`cases/cs-0004-a`, and `cases/cs-0004-b`. Within those directories it covers findings, source pairs, evaluator
oracles, reference probes, and harness material. It also covers Corsair-authored dataset annotations in this
directory, the manifest, and Corsair-authored qualification and technical-review receipts.

The same Apache-2.0 grant covers only the Corsair-authored files listed below for the sixteen real upstream cases.
Paths in the last two columns are relative to the named repository-root-relative directory. The authored inventory
is closed: four metadata/submission files per case plus exactly six curated locks, for 70 files.
The conformance source-pair grant above does not extend to source-pair bytes in these real cases.

| Case directory | Corsair-authored files covered | All bytes in these subtrees excluded |
| --- | --- | --- |
| `cases/cs-1001` | `input.json`, `oracle.json`, `reference-submission.json`, `asset-manifest.json`, `dependencies.lock` | `vulnerable/**`, `fixed/**`, `evidence/**` |
| `cases/cs-1002` | `input.json`, `oracle.json`, `reference-submission.json`, `asset-manifest.json` | `vulnerable/**`, `fixed/**`, `evidence/**` |
| `cases/cs-1003` | `input.json`, `oracle.json`, `reference-submission.json`, `asset-manifest.json` | `vulnerable/**`, `fixed/**`, `evidence/**` |
| `cases/cs-1004` | `input.json`, `oracle.json`, `reference-submission.json`, `asset-manifest.json` | `vulnerable/**`, `fixed/**`, `evidence/**` |
| `cases/cs-1005` | `input.json`, `oracle.json`, `reference-submission.json`, `asset-manifest.json`, `dependencies.lock` | `vulnerable/**`, `fixed/**`, `evidence/**` |
| `cases/cs-1006` | `input.json`, `oracle.json`, `reference-submission.json`, `asset-manifest.json` | `vulnerable/**`, `fixed/**`, `evidence/**` |
| `cases/cs-1007` | `input.json`, `oracle.json`, `reference-submission.json`, `asset-manifest.json` | `vulnerable/**`, `fixed/**`, `evidence/**` |
| `cases/cs-1008` | `input.json`, `oracle.json`, `reference-submission.json`, `asset-manifest.json`, `dependencies.lock` | `vulnerable/**`, `fixed/**`, `evidence/**` |
| `cases/cs-1009` | `input.json`, `oracle.json`, `reference-submission.json`, `asset-manifest.json`, `dependencies.lock` | `vulnerable/**`, `fixed/**`, `evidence/**` |
| `cases/cs-1010` | `input.json`, `oracle.json`, `reference-submission.json`, `asset-manifest.json` | `vulnerable/**`, `fixed/**`, `evidence/**` |
| `cases/cs-1011` | `input.json`, `oracle.json`, `reference-submission.json`, `asset-manifest.json`, `dependencies.lock` | `vulnerable/**`, `fixed/**`, `evidence/**` |
| `cases/cs-1012` | `input.json`, `oracle.json`, `reference-submission.json`, `asset-manifest.json` | `vulnerable/**`, `fixed/**`, `evidence/**` |
| `cases/cs-1013` | `input.json`, `oracle.json`, `reference-submission.json`, `asset-manifest.json` | `vulnerable/**`, `fixed/**`, `evidence/**` |
| `cases/cs-1014` | `input.json`, `oracle.json`, `reference-submission.json`, `asset-manifest.json` | `vulnerable/**`, `fixed/**`, `evidence/**` |
| `cases/cs-1015` | `input.json`, `oracle.json`, `reference-submission.json`, `asset-manifest.json`, `dependencies.lock` | `vulnerable/**`, `fixed/**`, `evidence/**` |
| `cases/cs-1016` | `input.json`, `oracle.json`, `reference-submission.json`, `asset-manifest.json` | `vulnerable/**`, `fixed/**`, `evidence/**` |

`input.json` contains independently written sanitized findings and Corsair request/source-pair metadata;
source paths and commit facts grant no rights in referenced source. `oracle.json` contains evaluator annotations,
provenance, tags, and expected outcomes. `reference-submission.json` contains independently authored hypotheses,
reference probes, fixtures created by those probes, and embedded build/harness scaffolding. There are no separate
case-local harness files in this inventory. `asset-manifest.json` covers Corsair-authored source/dependency
selection, hashes, path inventory, provenance annotations, and qualification bookkeeping; its license-expression
fields continue to describe third-party material under its separate terms.

The six covered `dependencies.lock` files are Corsair-authored dependency selection/hash metadata for
AnyIO/idna/sniffio (cs-1001), MarkupSafe (cs-1005), Number::Compare/Text::Glob (cs-1008), the four selected Requests
dependency wheels (cs-1009), and the jsr305 compiler artifact plus explicit jsoup source list (cs-1011), and the Commons Lang artifact plus explicit Commons Text source/resource
list (cs-1015). Their archive
or artifact URLs and hashes describe third-party packages; the grant does not cover the referenced archives, JARs,
wheels, or package contents.

All bytes under the table's `vulnerable/**`, `fixed/**`, and `evidence/**` paths are excluded from this grant.
Source closures, including supporting Starlette/Jinja/Requests modules, cs-1003's IOCase.java, cs-1007's crypto/util
closure, cs-1008's Number/Compare.pm and Text/Glob.pm, cs-1010's package metadata, cs-1011's three-file Java closure,
cs-1012's Module::ScanDeps source, cs-1013's eight-file PyJWT closure, cs-1014's EJS source/package closure,
cs-1015's Commons Text Java/resource closure, and cs-1016's HTML::Scrubber source in both revisions, are upstream
material, not Corsair harnesses.
The entire case evidence subtree is copied third-party material: GHSA JSON and CPANSA YAML advisories, source
licenses/notices, Net::Netmask distribution metadata/POD, File::Find::Rule source, CPAN dependency source,
and advisory/dependency licenses. Batch C evidence additionally includes generated Requests source/member inventories,
historical package/POM/build metadata, Requests and jsoup notices/licenses, jsr305 grant evidence and full Apache terms,
and Module::ScanDeps license-bearing distribution files. Batch D evidence includes PyJWT and EJS full license terms,
Commons Text and Commons Lang distinct licenses/notices and POM metadata, and HTML::Scrubber revision-local
README/dist.ini grants plus supplemental Artistic terms. Committing evidence does not make it Corsair-authored. Preserve upstream bytes,
notices, license expressions, URLs, revisions, hashes, and pending review decisions even when upstream separately
uses Apache-2.0.

Third-party wheels, sdists, tarballs, JARs, and other archives are excluded wherever acquired or cached.
`benchmarks/dataset/evidence/**` receives no blanket grant: runtime evidence can contain copied licenses/notices
and machine-collected facts. Only clearly identified Corsair-authored annotations fall under the existing
annotation grant; copied evidence does not. Future separately identified independently authored scaffolding
requires explicit scope when added. Preparation reports and upstream/generated source inventories are explicitly excluded from the authored-case grant.
These grants do not qualify a case or resolve third-party rights review.

That grant is limited to these benchmark assets. Unrelated repository code, upstream projects, runtime images,
runtime dependencies, test frameworks, coverage tools, and their transitive dependencies are not covered. Each
runtime row needs separate revision-pinned rights evidence and review before a case can be qualified.
