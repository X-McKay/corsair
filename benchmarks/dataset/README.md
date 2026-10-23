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
entries cannot carry it. Vendored rights evidence remains tied to the upstream repository and revision.

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

That grant is limited to these benchmark assets. Unrelated repository code, upstream projects, runtime images,
runtime dependencies, test frameworks, coverage tools, and their transitive dependencies are not covered. Each
runtime row needs separate revision-pinned rights evidence and review before a case can be qualified.
