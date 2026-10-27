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

The manifests passed on the command line are checked together as one population: an entry that appears in several manifests with the same split is no violation, and only a split disagreement is. The check reads each manifest and, for every entry that declares a split, its request after verifying the request digest (never an oracle); frozen sources and oracles are verified when a dataset is loaded or validated. It exits `1` on any of these violations:

- `family_crosses_splits`, `case_crosses_splits`: a family id or a case id in more than one split.
- `family_stem_crosses_splits`: two different family ids with the same family stem in more than one split. The stem is `<language>/<class>`: the language comes from an `ih-` or `chain-` prefix (`ih-perl-xss`), a leading language token (`js-prototypepollution`, `c-intoverflow`), or else the request's recipe kind (`xxe` under `java.secret_disclosure/1`), and the class drops `-` and `_`. So `xxe` and a later `ih-java-xxe` are both `java/xxe`. The violation names the stem, the raw family ids and their placement.
- `pair_crosses_splits`, `pair_crosses_families`: the two variants of a chain pair in more than one split or with different family ids. The pair is read from the request's directory with one layout rule ([`variant_stem`](../../src/corsair/evaluation/families.py)): trailing `v<N>` directories are skipped and the remaining directory is `<class>-a`/`<class>-b`, optionally suffixed `-v<N>`, so `chain/python/cmdi-a/`, `chain/java/xxe-b/v3/` and `chain/javascript/prototypepollution-a-v3/` belong to pairs `chain/python/cmdi`, `chain/java/xxe` and `chain/javascript/prototypepollution`.
- `source_tree_crosses_splits`: two entries in different splits whose `source.path` or `fixed_source.path` resolve (symlinks followed) to the same tree, to the same pair stem directory (a bare `a`/`b` corpus tree such as `corpus/infosec-harness/perl/xss/b`, or a tree inside a variant directory such as `chain/python/cmdi-a/source`), or declare the same `expected_digest` (a copied tree).
- `request_unreadable`: a labelled entry whose request is missing, escapes its root, no longer matches its declared digest or does not parse; the other rules cannot be applied to it.

`corsair.agent-dataset/1` manifests declare no family or split and are counted as unlabelled. `held_out.json` is the legacy listing of held-out family ids (`ih-<language>-<class>`, mapped to digests); each key is a family in split `held_out` with a stem from its id, and it has no request or source tree. The gym tiers copy their entries verbatim from the per-language and dev, safety and adversarial manifests, splits included, so they never contradict them; check a tier set on its own with `just dataset-families evals/datasets/gym-tier0.json evals/datasets/gym-tier1.json` (and `gym-tier2.json` once a reviewed holdout exists), and every manifest together with `just dataset-families`. On the checked-in manifests both runs pass with no violation (20 families and 20 stems across all manifests; 12 and 12 across the two tiers). This is still a weak statement: `held_out.json` carries no runnable request or oracle, family ids are spelled inconsistently across manifests (`chain-python-cmdi`, `js-prototypepollution`, `ih-perl-xss`, bare `xxe`), which the stem rule only compensates for, and most lite chain rows under `datasets/chain/` belong to no manifest yet. A runnable held-out cohort needs a `corsair.dataset/1` manifest whose entries use the corpus family ids.

Composed reports written by `corsair eval` and `corsair rescore` carry each row's `family` and `split`. `corsair report REPORT --families` and `corsair compare BASELINE CANDIDATE --families` add per-family and per-split pass, decisive and forbidden-label summaries, and every compared case and regression names its family, so a regression is attributable to a vulnerability class. Older reports are labelled with `--dataset MANIFEST`, which must be the exact manifest (by dataset digest) the report was scored against; the candidate records in `candidates/v3-live-20261026` were scored against the manifests at 5f814341, not the current ones. Record the families and splits a candidate exercised with any promotion request.
