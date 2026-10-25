---
id: HANDOFF-0146
kind: handoff
title: Local storage inventory, retention proposal and ignore safeguards
status: implemented
updated: 2026-10-25
related: [PLAN-0114, HANDOFF-0145, ISSUE-0010]
---

# Local storage review

The user asked what to clean, keep and use under .runs, .work and .state. Inventory was metadata-only. No private settings, key, model-trace or artifact contents were opened, and no saved data was moved or deleted. The [retention plan](../plans/PLAN-0114-local-storage-retention.md) is still proposed; it is not consent to purge evidence or reset state.

The snapshot measured roughly2.1GiB allocated. .work dominates at1.81GiB; repeated test temp trees are973.69MiB logical, a dependency cache332.59MiB, the validated task venv317.25MiB, and other useful logs/checkpoints/databases just7.05MiB. Recent run evidence is tiny; keep it intact. Old Temporal CLI downloads under .state are not persistence, while actual Temporal history databases were found under .work task folders. Legacy Ollama TLS/configuration may still be used; its private keys and owner context must not be discarded to fit a cleaner tree.

Only two reversible changes were implemented: root .gitignore now ignores .work/, and Docker's narrow default-deny allowlist now names the actual trusted driver path under src/corsair/adapters/sandboxing. The previous allowlist still named the retired tools/security path. Rebuilding the image verified the corrected context;7 real Docker conformance tests passed with0 skips in23.78s. Runtime source, SDK/provider settings, frozen inputs, policies and pins did not change. No provider calls or saved-data cleanup were performed. Private roots remain excluded from source packages.

The prior eval/test directory cleanup is recorded in [HANDOFF-0145](HANDOFF-0145-eval-test-layout.md):133 native non-live tests passed,103 offline tests passed after cleanup, all134 collection IDs/order preserved and29 pre-existing eval files byte-identical. The7 Docker checks above qualify the later build-context fix separately; they are not a new live-model result. The original main stash and local uncommitted manus/just work remain untouched by publication.

User-facing files are outputs/local-storage-review-20261025/PROPOSAL.md and housekeeping-verification.json. A refreshed source/report bundle includes current ignore fixes, not only git HEAD. Private review evidence remains under .work/local-storage-review-20261025. No commits, pushes, release or deployment were performed. The next action is to discuss an exact first-stage deletion scope; do not delete the working venv, any actual Temporal database, run artifact store, TLS material or old provider state based on this proposal alone.
