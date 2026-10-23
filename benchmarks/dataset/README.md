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

The `quarantine` split is never scored. A public repository is not license evidence, and missing, conflicting,
noncommercial or `NOASSERTION` material remains quarantined until separately resolved.
