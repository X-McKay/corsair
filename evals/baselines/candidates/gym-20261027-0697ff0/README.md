# Candidate record: evaluation-gym wave-1 reference (2026-10-27)

AI-authored candidate diagnostic pending human review; not a baseline, nothing promoted. Produced by `corsair gym run`
on `gym/loop` at 0697ff08 with repeats 3, concurrency 2, Temporal namespace `corsair-gym`, real Docker images with
content-addressed tags, and `hosted_vllm/Qwen3.6-35B-A3B-NVFP4` for both roles (one shared local endpoint; no other
live runs overlapped tier1). Identity 34f22f5e…, budgets 63137bce… (`evals/experiments/budgets.json`), datasets
tier0 97fc4873… (6 cases) and tier1 ec8cd985… (15 cases). Files: `tier0-scorecard.json`, `tier1-scorecard.json`,
`run-details.txt` (run directories, image ids, wall times).

Headline: tier0 J 1.4554, verified accuracy 1.0 in all six languages; tier1 J 1.4025, macro verified accuracy
0.9667, worst language python 0.80, macro effective tokens 37,079, macro p50 57.9 s. Limits: small n (one case per
non-Python language), majority-of-3 aggregation, latency under a shared endpoint, cached tokens never reported by the
provider, thought tokens counted inside output tokens on this route, Java sandbox host seconds about 4 s per role.
Raw reports and trajectories stay private under `.runs/gym/` in the `gym/loop` worktree.
