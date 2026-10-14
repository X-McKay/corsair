# Independent probe specialists: curated consequence cases

This eval-only corpus contains four tiny Python/pytest use cases: SQL row disclosure through actual
SQLite, outside-root document disclosure through actual temporary files, sensitive-field disclosure in
a returned public profile, and unauthorized state mutation before denial. Each case captures complete
reported/fixed source inventories, an existing ordinary convention test, distinct role tasks and resolved
native identities. These are synthetic examples, not a representative security benchmark. They add no
language/CWE-specific tool or runtime-policy branches.

`cases-v1.json` is an operator envelope. `revision_inputs` projects exactly one captured revision without
its label; dedicated role projectors remove the other role's task and writable identity/path. The shared
property carries separate benign behavior and safety property. Reported consequence and supported scope
are explicit operator fields. `rubric-v1.json`, paired revisions and `reference-patches-v1.json` stay
operator-only. Do not include them in agent prompts. `manifest-v1.json` binds the three frozen data
artifacts. This freeze incorporates the user's consequence-observation clarification before any model
measurement or native calibration; future measured artifact changes require a new version.

Each reference pair contains exactly one control and one exploit expressed as a safety regression.
Controls call the actual component and assert expected ordinary behavior on both revisions. Exploits
exercise the reported condition and assert absence of the concrete unauthorized consequence. The SQL
fixture seeds distinct authorized/unauthorized balances and uses the real sqlite3 engine; no database
double hides parsing behavior. Path fixtures create a contained public file and an outside-root secret,
then the reader actually reads bytes without enforcing containment. Profile tests inspect the actual
returned dictionary. Authorization tests inspect actual supplied state and the specific PermissionError;
both revisions deny, but mutation before denial violates the state snapshot. No generated test or copied
target replaces the production property logic.

Scope remains narrow: the selected SQLite query/engine, lexical POSIX traversal in controlled temporary
files without symlinks, a returned public-profile dictionary, and synchronous supplied state. No wider
transport authorization, HTTP serialization, shell execution, engine portability, persistence, symlink
races or concurrency claims follow. The process-construction recorder example was replaced with direct
output disclosure because construction observations alone would not establish executable consequences.

Reference outcomes in the frozen rubric remain expected oracle labels. Subsequent independent review and native calibration passed all four pairs on both captured revisions, with cleanup confirmed; receipts are retained outside Git under `.runs/probe-specialists/`. Source-only reference
rationale is recorded in the rubric; independent review must confirm it. Source inspection is not
execution qualification. Before calibration or generated-test execution, independently review frozen
source/patch/property linkage without outcomes, bind complete inventories and patch hashes, then run
both unchanged probes on both revisions through restricted Docker/native execution. Generated code
must not execute on the host. Failed control, skipped/unknown execution, discovery failure or an
unfaithful fixture cannot establish an application fix or false-positive conclusion. Passing model-authored
assertions alone cannot establish semantic validity.

Compare distinct agents in isolation on the host with typed ports; keep sandbox execution qualification
separate. Report per-role validity and actual outcomes, contract/task failures, latency, requests, tools,
tokens, retries and telemetry gaps. Repetitions measure consistency within these examples rather than
broader framework, language or CWE generality. Baseline promotion and production adoption require
separate measured decisions.

## Commands and measured comparison

Use the existing locked Python environment with `PYTHONPATH=src:.`:

```sh
python -m evals.experiments.probe_specialists.evaluate --agent control --evidence .runs/control-scripted
python -m evals.experiments.probe_specialists.evaluate --agent exploit --evidence .runs/exploit-scripted
python -m evals.experiments.probe_specialists.evaluate --agent all --repeat 1 --provider-config /path/to/provider.json --evidence .runs/probe-comparison
```

Omitting provider configuration runs scripted SDK plumbing only. Live agents receive neither reference answers nor labels. Each specialist has its own20 requests/20 tools/128000 tokens/900 seconds and2 output retries; the joint baseline receives their sum and the identical instruction/skill union. Independent drafts never consume a peer artifact; composition is operator-owned. Source-only review then restricted native execution tests each role with a frozen reference counterpart and tests the generated pair separately.

Normal unit mocks, fakes and fixtures are appropriate for either role; these four fixture choices follow their particular consequence scope. No universal real-dependency requirement follows. See [comparison report](../../../docs/qualification/probe-specialists-comparison.md) for original scores, a separately retained source-feedback correction and limits. These remain eval-only prototypes; no production route, baseline promotion or DynamicWorkflow adoption is implied.
