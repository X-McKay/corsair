---
id: SPEC-0069
kind: spec
title: Runtime inferred from framework metadata when undeclared
status: draft
updated: 2026-10-13
related: [SPEC-0042, SPEC-0067, SPEC-0060, PLAN-0076]
---

# Runtime inferred from framework metadata when undeclared

## Goal and scope

SPEC-0042 makes a project that declares no runtime version undetermined. That stops 35 of the 42 SPEC-0067 corpus cases, and many real repositories are in the same state: a bare `requirements.txt` naming `pytest`, or a `package.json` naming only `jest`. Al chose to generalise Corsair rather than edit the corpus (decision card, 2026-10-13 15:51Z), and agreed to this refinement (15:52Z): use the declared version when there is one; otherwise infer a range from the declared dependencies and take the newest qualified image inside it; record that the runtime was inferred and from what; stay undetermined when nothing gives a range.

In scope: inference from the declared test framework. Al's 15:52Z wording also allowed a range from language syntax; that is not implemented here, so such a project stays undetermined. Out of scope: inference from other dependencies or from language syntax, a framework for projects that name none (Node's built-in runner is still unidentified), and the operator smoke test for projects with no tests (next component).

## Boundaries and design

**Inference rows.** `deploy/runtime-matrix.yaml` gains an operator-owned `inference` list. Each row says which runtime versions a framework release range supports, copied from that release's own published metadata, and cites it: PyPI `requires-python` for pytest, npm `engines.node` for Jest, `MIN_PERL_VERSION` for Test::More, rubygems.org `required_ruby_version` for Minitest. A row never says what a project needs. The loader refuses a row whose runtime no image row of that language provides, and an empty set. Projects and agents never edit it, like the rest of the matrix.

**When inference applies.** No runtime declaration was read, no runtime line was seen and left unread, the matrix has inference rows, and a test framework is identified. Otherwise selection is exactly SPEC-0042's. A declared runtime is never replaced. An unread runtime constraint (`requires-python = 313`) still makes the result undetermined, and so does an unread framework constraint, since either could exclude every inferred range.

**Selection.** Image rows of the language are tried newest runtime first. A row is selected when every declared image tool matches and some framework version is in the project's range, the row's qualified range and an inference row whose runtime range contains the row's runtime. The result is `Supported` with `runtime_basis: inferred` and `inferred_from` naming each inference row used. Its runtime check carries the inferred range, and its framework check carries the overlap that setup must pin inside. When inference rows cover the framework but no image fits, the result is `unsupported`, naming the runtime range those rows allow and the framework. When no inference row covers the framework's range, the result stays undetermined and says so.

**Recording.** The runtime stage's reason says the runtime was inferred and from which rows. The SPEC-0042 report prints such cases as `supported (runtime inferred)`, beside the image-only marker from #92. A run's evidence therefore always shows whether the runtime came from the project or from framework metadata. "Never a nearby version" stands: the range is what the framework's own release declares, and the selected row's exact runtime must lie inside it.

## Acceptance and validation

Offline unit tests:
- An unpinned pytest takes the 3.12 row, inferred, pinned to 9.0.*.
- `pytest<8` takes the 3.7 row.
- A declared runtime stays declared.
- An unread runtime or framework constraint stays undetermined.
- Jest 29 names the Node range it needs.
- Vitest, with no inference row, stays undetermined.
- No framework keeps both gaps visible.
- Perl without a version infers from Test::More.
- A row for an unprovided runtime is refused.
- With no inference rows, selection is unchanged.

The regenerated report shows the benchmark outcomes unchanged and the corpus moved from undetermined to supported where a row covers the framework. Selection is metadata only; a supported inferred case still needs its run.

## Decisions and open questions

- Only the test framework is used for inference, because it is the one dependency the detector already reads with versions and the one every run installs. Other dependencies can narrow the range later.
- Newest qualified image first, as agreed; image-only rows can be selected, and the report marks them.
- Open: syntax-based lower bounds; an inference row for Node's built-in test runner once the detector identifies it; the smoke-test component for projects without tests.
