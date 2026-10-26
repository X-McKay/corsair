# Evaluation records

No population-level accuracy, low false-positive rate, production baseline, or automated promotion is claimed. The authored fixtures provide deterministic native conformance, isolated agent diagnostics, and small end-to-end smoke tests.

- [Qualifications](qualifications/README.md) holds sanitized qualification records once they are produced. Each record's bytes and its stated limitations are preserved as written.
- [Candidates](candidates/README.md) holds AI-authored candidate diagnostics pending human review. Candidate diagnostics are not baseline records and do not establish a held-out, human-labelled, or promoted baseline.

Store raw private reports under `.runs/`. Promote a sanitized baseline only after repeat runs on frozen, human-labelled, family-grouped held-out data, with the exact source/recipe/image/model/instruction/tool/schema/budget identities and cohort recorded. A scripted runner passing is not a live-model baseline.
