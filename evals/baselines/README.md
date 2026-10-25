# Evaluation records

No population-level accuracy, low false-positive rate, production baseline, or automated promotion is claimed by this pilot. The initial authored fixtures provide deterministic native conformance, isolated agent diagnostics, and small end-to-end smoke tests.

- [Qualifications](qualifications/README.md) contains historical, sanitized qualification records. Their location is organizational only; each record's bytes and historical limitations are preserved.
- [Candidates](candidates/README.md) describes AI-authored candidate diagnostics that are pending human review. Candidate diagnostics are not baseline records and do not establish a held-out, human-labelled, promoted, or population baseline.

Store raw private reports under `.runs/`. Promote a sanitized baseline only after repeat runs on frozen, human-labelled, family-grouped held-out data, with the exact source/recipe/image/model/instruction/tool/schema/budget identities and cohort recorded. A scripted runner passing is not a live-model baseline.
