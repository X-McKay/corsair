# Reports that do not hold at the reported revision

Each request here is a corpus case's issue text pointed at the case's own not-exploitable variant: `revision` and `fixed_revision` are both the commit `evals/corpus/issues/<case>/issue.json` names as its fix. The chain should end `completed / not_reproduced / not_verified` (LIKELY_NOT_EXPLOITABLE); `not_verified` because nothing was reproduced, so no fix can be verified. They exist so a negative verdict can be produced from the Python cohort today: the cohort's two unpaired cases (`ih-python-healthcheck`, `ih-python-queryhelper`) name no fixed revision and `corsair run` refuses them ("a vulnerable-only run is not built yet").

| Request | Why it can reach `not_reproduced` |
|---|---|
| `ih-python-pathtraversal.json` | `read_doc` raises `ValueError` before opening a path outside `data/`; the `audit_open` witness records the planned file's absence and the target's exit. |
| `ih-python-xxe.json` | Probe of the absence path: the parser never opens the external entity and returns normally, so the plan's safe behavior must be `no_file_open`, which stays `inconclusive` on the baseline until SPEC-0040's control calibration lands. Expected INCONCLUSIVE today. |

`repository` is checkout-relative like the corpus cases, so `corsair run --issue-json evals/corpus/negative/<case>.json` runs from this checkout. Answer keys stay in this README, never in what an agent reads.
