# Corsair lite

Corsair validates a reported security issue against an exact source revision and, when one exists, its fix. This
branch is the minimal redesign: a **deterministic verdict kernel**, one **producer** agent and one **outcome-blind
auditor**, instead of a five-stage agent pipeline.

The producer explores the vulnerable tree in its own sandbox and submits one *differential probe*: a hypothesis
(file, function, lines, mechanism), a build script, and a Python module defining `CONTROL_PAYLOAD`,
`EXPLOIT_PAYLOAD` and `run_target(payload)`. The kernel then, in containers the producer never touched:

1. checks the probe's structure (three symbols, one payload argument, no mocking libraries);
2. replays the build script in a clean container with network, removes the network, seals the image;
3. runs `run_target(CONTROL_PAYLOAD)` alone as a native pytest test under coverage: it must hold and execute the
   hypothesis' target lines;
4. runs `run_target(EXPLOIT_PAYLOAD)` alone: it must fail with the probe's own assertion (the invariant was
   violated, so the reported condition occurred) and also execute the target lines;
5. asks the auditor, which sees only the hypothesis and probe, whether the probe is a fair test;
6. for an exploitable submission with a fixed revision, repeats steps 2 to 4 there to decide whether the fix is
   verified.

Any failed gate goes back to the producer as the reason, and it may resubmit within an operator-owned budget. The
label is `LIKELY_EXPLOITABLE` (K1) when every gate passed on the vulnerable revision. It is `LIKELY_NOT_EXPLOITABLE`
(K4) when `--negative-threshold` distinct submissions (default 2) were clean negatives: control held and the exploit
payload held, both executing the target lines and the audit accepted. The producer then stops early. Otherwise the
label is `INCONCLUSIVE`, `UNABLE_TO_RUN` or `ERROR`. A fixed revision, when the case has one, is checked only for an
exploitable submission and only annotates the verdict (`fix`); it never changes the label.
One driver with two payloads makes "both probes exercise the same real seam" true by construction, and the kernel
still produces two native test ids (`test_probe[control]`, `test_probe[exploit]`), a JUnit report and a coverage
report per run.

## Commands

Requirements: Linux, Python 3.12, `uv`, Docker.

```shell
make sync            # install
make test-offline    # scripted model and sandbox doubles; no Docker, no model
make test            # plus the kernel on real containers (builds images/python)
make verify          # kernel only, on the reviewed fixture with the reference submission
make investigate CASE=cases/path-traversal-fixture PROVIDER=config/providers.local.json
make eval            # the pilot set against their oracles; writes .runs/lite/eval-<stamp>.json
make eval-dev        # the dev split (evals/e2e/sets/python-v2-dev.json); REPEATS=N runs each case N times
make eval-heldout    # the held-out split (evals/e2e/sets/python-v2-heldout.json); report only, see below
make cleanup         # remove every container this tool created
```

Every run writes `.runs/lite/<run id>/run.json` with each submission's gate, the probe runs (outcomes, exception
types, covered lines, JUnit and log references), the verdict and the producer's usage. `oracle.json` files beside
cases are evaluator-only and never reach the agents.

## Measuring accuracy

`make eval` scores cases against their oracles; the eval summary (`.runs/lite/eval-<stamp>.json`) reports:

- `metrics`: accuracy over scored runs (the oracle's accepted labels), per-label precision and recall for
  `LIKELY_EXPLOITABLE` and `LIKELY_NOT_EXPLOITABLE` (truth is the oracle's `expected_label`), the `INCONCLUSIVE` rate,
  label counts and usage (requests, tokens, tool and bash calls, duration). A field no run reported is `null`
  (unknown), never zero; `reported_runs` says how many runs supplied it.
- `per_case`: for each case over its repeats, the label counts, the modal label, `agreement` (share of runs on the
  modal label) and accuracy.
- `models`: the profile, model name, endpoint and sampling settings each agent ran on.
- `runs`: one row per investigation, with its `run_id` and the full record under `.runs/lite/<run id>/`.

`--repeats N` (`REPEATS=N` on the Makefile targets) runs every case N times. A single run of a stochastic model says
little about accuracy; repeats show whether the label is stable as well as correct.

**Splits.** `evals/e2e/sets/python-v2-dev.json` (20 cases, 10 families) and `python-v2-heldout.json` (10 cases, 5
families) partition the 30 paired Python v2 cases: each family's `-a` and `-b` variants are in the same split, and each
split holds one exploitable and one safe variant per family. The split is frozen: families are sorted by name and every
third one is held out. The set files record a sha256 of each oracle, and `--set` refuses a set whose oracle has
changed. **Held-out cases are for reporting only.** Do not use them to tune prompts, skills, budgets or contracts, and
do not read their failures to change the agent. Tune on dev, freeze the configuration, then run held-out once for the
report. Compare results only across runs with the same set, `REPEATS`, `MAX_SUBMISSIONS` and negative threshold.

**Models.** The model is chosen by the provider config, not by a flag, so each model gets its own config file with the
same agent mapping and only `model_name` (and endpoint) changed, and each run names it:

```shell
make eval-dev PROVIDER=config/providers.model-a.json REPEATS=3
make eval-dev PROVIDER=config/providers.model-b.json REPEATS=3
```

Keep those files out of version control if they name private endpoints. Credentials are never stored in the config:
`api_key_env` names an environment variable. The summary's `models` section is what makes two result files comparable.

## Layout

```text
src/corsair/
  case.py        Case, Finding, Revision (tree digest), request loading; oracles kept separate
  matrix.py      matrix.yaml rows: image + framework + detection hints
  providers.py   operator model profiles (OpenAI-compatible endpoints), two agents, no fallback
  sandbox/       the Sandboxes port and its Docker adapter (hardened containers, labels, environments)
  kernel.py      gates, twin runs, verdict
  auditor.py     the blind auditor agent
  producer.py    the producer agent and its three tools
  cli.py         verify / investigate / eval / cleanup
  skills/        operator-owned Markdown the producer may read
images/python/   the pilot runtime image
matrix.yaml      the runtime matrix
cases/           the reviewed fixture case with its reference submission
evals/e2e/python Local Python corpus cases (input.json + evaluator-only oracle.json)
benchmarks/      the fixture trees and the Python corpus they point at
docs/            design.md (why and what), pilot.md (what was run and what happened)
```

## Scope and honesty

The sandbox is Docker on the host (the image-only tier); the production sandbox is OpenShell behind the same port and
is not part of this branch. The pilot image runs as root inside a hardened container. Only pytest is supported;
other languages arrive as matrix rows plus driver templates. `LIKELY_NOT_EXPLOITABLE` is emitted only under K4, and a
single clean negative proves nothing about absence, which is why the threshold is an operator setting. K4 is
implemented but not evaluated against a live model: the offline tests exercise it with scripted doubles only, so its
precision is unmeasured. Results in `docs/pilot.md` are from the operator's local model and are small-n and predate K4.
