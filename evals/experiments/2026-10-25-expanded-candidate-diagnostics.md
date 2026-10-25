# Expanded candidate diagnostic packets

Date: 2026-10-25. This is an AI-authored candidate-diagnostic design record, pending human review. It records frozen fixture construction and offline consistency validation only; it is not a live-model experiment, a native execution result, or a qualification record.

The producer manifest `datasets/producer-expanded.json` retains the original `case01` input and oracle identities, and adds `producer02` and `producer03`. The auditor manifest `datasets/auditor-expanded.json` retains the original `audit01` and `audit02` identities, and adds `audit03` and `audit04`. The new producer packets use distinct standard-library targets (`pathlib.Path` / `read_document` and `os.path.join` / `fetch_record`) and distinct fixed keyword arguments. Their payloads are exact scalar path values, not keyword-argument maps.

| Manifest | Raw SHA-256 | Canonical evaluator digest | Entries |
| --- | --- | --- | ---: |
| `datasets/producer-expanded.json` | `3ef07e3de4f15d0d4cd126fc0810f24cf8de33a2464cc0a0c3e7ad24cfd4df94` | `a2a6907fd06dc09003558ecfbe844f7659acc75ffa2a82a2feca4e150c74a3e2` | 3 |
| `datasets/auditor-expanded.json` | `43ffbc384e60931272e7115107a3cd77b1e66ea9ae76ae1cc664d868f1fae389` | `b7284e237d2dce26f2f5a4719af4a7e9520ee750bad8fb5a9abd312946437bc7` | 4 |

The new producer packet raw identities are `producer02`: input `d9d2f92a13a274a1eaf5f73f1cbc0c21ea759c5843dd364cbfbb5c4eab1cfb5a`, oracle `1b0dae93873d5ad14d36e3d8647e7273e80476e5e1e11b5029cb9855720eba7a`, admitted source snapshot `c42aaf19a554caae66bdf0ab15b96381a4515c355e42a9a18748f623bd2e0a1c`; and `producer03`: input `4e0f5eece58e2f68c32c60aec65516e3adb84d6ca405772b29f5dababa748efa`, oracle `45a5f3eeebc7af5aacb19c02690fd9b25325fdf372d2ed67a86b8e96402f1237`, admitted source snapshot `95bc5fee1e57929fc24f022494a93747e47d1e1800266a661ff43eff9d534950`. The auditor packets are `audit03`: input `6b9d32c805c482dea3c4973f3e00745e337b67a019ad9687ee71475634b86f1b`, oracle `374257696b602b3252f2e1fb7340ecd8630e1fcf53820260d04b884bed126f4f`; and `audit04`: input `0406ab74bf542ed2de3b4977594fa21a83eb1aa424001cceda3d54afe501d61e`, oracle `7db730fa160fd72c8613962722bd63d70ba5dec5627c5c93aefa3fe0a29c4424`.

`audit03` has an external `ACCEPT` oracle for a source-grounded parent-traversal proposal. `audit04` has an external `REJECT` oracle because its SQL mechanism is fabricated relative to the supplied `os.path.join`/`open` source. The labels are absent from each agent input; they remain evaluator-only comparison data.

The offline validation command `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .work/mac-e2e-20261025/venv/bin/python -m pytest tests/unit/test_expanded_evals.py -q` passed 4 tests in 2.85 seconds. It parses the packets through canonical Pydantic contracts, verifies exact raw input/oracle bytes through the installed evaluator loader, and checks both producer source snapshots with the canonical local snapshot loader. It deliberately does not import or execute a target, invoke a model, use Docker or Temporal, or create native evidence.

These AI-authored candidate diagnostics are not human-labelled, held-out, promoted, or population baselines. They establish no accuracy, false-positive, negative-clearance, Docker, Temporal, host-loss, or production-readiness claim. Any promotion needs independent human review and labels, family-grouped held-out cohorts, explicit configuration identities, repeated actual runs, and a separate sanitized record.
