# Agentic intake image selection

Status: authorized by the user's 2026-10-28 request for an image-selection agent tool and skill. Continue the scanner/JSON robustness work in PLAN-0135; retain all completed variants before this capability change.

## Design

The agent owns interpretation and image choice. Add a role-local `compare_images` tool bound to the trusted, currently available inventory snapshot. It accepts canonical language/mode/requirement categories, exposes each image's reviewed capabilities, matches and missing requirements, and reports uncertainty or forbidden requirements. It does not choose a final image, discover registries, pull/build images, execute commands, infer unreviewed capabilities or grant permissions. Agent proposals and trusted policy remain separate.

Add one packaged `image-selection` procedural skill under `agents/intake/skills`. Preload its reviewed instructions through native ADK (as existing roles do), with private native refresh loaders. Guidance covers source-grounded requirements, comparing candidates, reconsidering unnecessarily broad requirements using inspected source, honest unknowns, exact inventory references and categorical blockers. No scanner recipe gates or special-case answers.

Canonical agent output remains IntakeProposal. Extend bounded tool-count accounting to include this actual helper; skill preload and model-requested loads remain distinguishable. Existing total call/output/time budgets remain unchanged. Hash the helper and skill resources into the intake identity; load everything from the built package.

## Work

- [x] Red/green direct tool cases: compatible, missing capabilities, unknown requirements, empty inventory, denied network/privileges, duplicate/invalid categories, mutation isolation and output limits.
- [x] Red/green genuine native ADK case: use comparison tool and optional skill loader, complete canonical output, record actual calls/preload, enforce existing budgets. Update metadata and installed-wheel assertions.
- [x] Implement native role-local helper/skill/factory/accounting and packaged identities. Preserve read-only source tools and current inventory authority.
- [x] Fresh scoped review; affected quality/offline/native tests and wheel/resources outside checkout.
- [x] Evaluate unchanged original and scanner cohorts at the same configured endpoint, keeping this capability identity separate. Report actual tool use independently from accuracy; absence of tool calls is not tool benefit.
- [x] Record actual results and unrun limits. The scanner candidates are not held-out baseline evidence; ambiguous-report failures remain explicit. No commit or publication.

## Recorded implementation and live result

Eleven regressions were observed red before implementation. The final focused suite passes **30 tests** including nonempty/empty inventory through both native schema paths and the single-refresh limit. Fresh read-only review found no important defects; its positive-inventory coverage suggestion was implemented. Pre-final offline sweep passed 361 tests, 81 deselected; the final expanded sweep and native/package gates are recorded below.

The completed scanner repeat scored **46/64 exact, 57/64 correct decisions, one false-supported, zero invalid outputs/model failures**. The separate original cohort scored **4/8 exact, 6/8 correct decisions, one invalid output and one model failure**. Every episode preloaded `image-selection`, while the live model made **zero actual tool calls**. No invocation benefit or overall model reliability is claimed. Resource identity is `e11cf4391d94e68a9e9caaa306c43fb134e3de58f03e58ece626bc2ca6f12ce3`; provider/model, frozen cases/oracles, inventories, budgets and scorer were unchanged. The 32-case scanner corpus is authored and correlated, not human-reviewed held-out data. All failed variants and unknown costs remain retained.

Commands used the same `corsair.evaluation.intake.evaluate` entry point sequentially: original dataset once and scanner revision 2 twice, with `.state/intake-json-20261028/settings.json`, 60-second ceilings and separate `.runs/intake-json-20261028/original-image-tool.json` / `image-tool-v2.json`. Source and generated target code never ran on the host. See [sanitized result](../../../evals/experiments/2026-10-28-intake-image-selection.md).

Final gates before the dependent workflow work: `nix develop --command just check` passed; `nix develop --command env TERM=xterm-256color just -- test -q -W error` passed **365 tests, 81 deselected**, 13.49s; the unchanged 11-test real Docker/Temporal/replay selection passed **11, one live test deselected**, 28.91s. `nix develop --command just build` succeeded with the existing uv version-range warning. Wheel and sdist each have **151 clean entries**, no private/cache paths, and wheel source/resource bytes match the implementation. Installed-wheel resources outside checkout are included in the offline gate. Nothing was committed or pushed. Model use and remaining reliability are explicitly unqualified despite implementation completion.
