# Reports that do not hold at the reported revision

Each request here is a corpus case's issue text pointed at the case's own not-exploitable variant: `revision` and `fixed_revision` are both the commit `evals/corpus/issues/<case>/issue.json` names as its fix. The expected result is per request, in the table: a request that can reach a negative verdict ends `completed / not_reproduced / not_verified` (LIKELY_NOT_EXPLOITABLE), `not_verified` because nothing was reproduced, so no fix can be verified. They exist so a negative verdict can be produced from the Python cohort today: the cohort's two unpaired cases (`ih-python-healthcheck`, `ih-python-queryhelper`) name no fixed revision and `corsair run` refuses them ("a vulnerable-only run is not built yet").

| Request | Expected result and why |
|---|---|
| `ih-python-pathtraversal.json` | LIKELY_NOT_EXPLOITABLE: `read_doc` raises `ValueError` before opening a path outside `data/`; the `audit_open` witness records the planned file's absence and the target's exit. |
| `ih-python-xxe.json` | INCONCLUSIVE, a probe of the absence path: the safe parser never opens a file and returns normally, so the plan's safe behavior must be `no_file_open`. SPEC-0040 calibration (PLAN-0084) needs the control's call to record its own file open, and no benign input makes this parser open one, so the absence cannot be calibrated. |

`repository` is checkout-relative like the corpus cases, so `corsair run --issue-json evals/corpus/negative/<case>.json` runs from this checkout. Answer keys stay in this README, never in what an agent reads.
