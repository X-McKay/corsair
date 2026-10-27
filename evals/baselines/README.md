# Evaluation records

No population-level accuracy, low false-positive rate, production baseline, or automated promotion is claimed. The authored fixtures provide deterministic native conformance, isolated agent diagnostics, and small end-to-end smoke tests.

- [Qualifications](qualifications/README.md) holds sanitized qualification records once they are produced. Each record's bytes and its stated limitations are preserved as written.
- [Candidates](candidates/README.md) holds AI-authored candidate diagnostics pending human review. Candidate diagnostics are not baseline records and do not establish a held-out, human-labelled, or promoted baseline.

Store raw private reports under `.runs/`. Promote a sanitized baseline only after repeat runs on frozen, human-labelled, family-grouped held-out data, with the exact source/recipe/image/model/instruction/tool/schema/budget identities and cohort recorded. A scripted runner passing is not a live-model baseline.

## Configuration identity after the transport-free change

Since [PLAN-0003](../../docs/plans/active/PLAN-0003-evaluation-gym.md) WP3, `Settings.identity` (each result manifest's `config_digest`) excludes the transport and storage fields `temporal_address`, `temporal_namespace`, `task_queue`, `artifact_root` and `source_root`, so a gym run's per-run task queue or Temporal port no longer changes it. Every record made before the change, including the candidates under `candidates/`, carries a configuration digest computed with those fields, so the same settings now produce a different digest. Do not read a digest difference across the change as a behaviour change, and do not mix the two in one comparison without saying so. No record was promoted, and none is rewritten.

## Checking the family-grouped split

The family rule is checkable; run it before treating any split as held out:

```bash
just dataset-families                      # every manifest under evals/datasets/
just dataset-families evals/datasets/dev.json evals/datasets/held_out.json
```

It reads manifest membership only (frozen bytes are verified when a dataset is loaded) and exits `1` when a family, a case or a chain pair (request directories `<class>-a` and `<class>-b` under one parent) appears in more than one split, or when the two variants of a pair carry different families. `corsair.agent-dataset/1` manifests declare no family or split and are counted as unlabelled. `held_out.json` is the legacy listing of held-out family ids (`ih-<language>-<class>`, mapped to digests); each key is a family in split `held_out`. On the checked-in manifests the check passes with no violation, but this is a weak statement: `held_out.json` carries no runnable request or oracle, its family ids share no namespace with the composed manifests (`family01`, `safety01`, `adversarial01`), and the lite chain rows under `datasets/chain/` belong to no manifest yet. A runnable held-out cohort needs a `corsair.dataset/1` manifest whose entries use the corpus family ids.

Composed reports written by `corsair eval` and `corsair rescore` carry each row's `family` and `split`. `corsair report REPORT --families` and `corsair compare BASELINE CANDIDATE --families` add per-family and per-split pass, decisive and forbidden-label summaries, and every compared case and regression names its family, so a regression is attributable to a vulnerability class. Older reports are labelled with `--dataset MANIFEST`, which must be the exact manifest (by dataset digest) the report was scored against; the candidate records in `candidates/v3-live-20261026` were scored against the manifests at 5f814341, not the current ones. Record the families and splits a candidate exercised with any promotion request.
