# Polyglot security-regression benchmarks

`benchmarks.polyglot.generate(root, languages=None)` creates deterministic, synthetic **twin-revision** Corsair fixtures. It is a compact policy-template benchmark generator, **not** an external vulnerability-corpus catalog and **not** a claim that the sources are real vulnerable frameworks, real exploit chains, or distinct CVEs.

## Stable generator contract

```python
from pathlib import Path
from benchmarks.polyglot import generate

case_paths = generate(Path("/tmp/corsair-polyglot"), languages=["python", "java"])
```

- `root` is a caller-selected writable directory. The generator creates it when absent and deterministically overwrites only matching generated fixture files; it does not delete unrelated files.
- `languages` is optional and accepts lowercase names from `python`, `java`, `javascript`, `typescript`, `perl`, `ruby`, and `cpp`.
- The return value is a stable-order `list[Path]` of **case directories**, each directly acceptable to `corsair.application.cases.load_case`.
- Each case has `input.json`, `reference-submission.json`, `provenance.json`, `oracle.json`, and `vulnerable/` plus `fixed/` source trees. `oracle.json` is evaluator-only and is absent from both the Case request and Submission.

Every target exposes a small command-line policy API that evaluates its supplied raw request and writes `ALLOW` or `DENY`; it is a policy computation in language source, not a stored expected-result marker.

The shared Python probe stores **ordinary raw strings** in `CONTROL_PAYLOAD` and `EXPLOIT_PAYLOAD`; there is no `Request` wrapper or `forbidden` input tag. For each family the generator renders a pure, independently value-derived `safe_predicate(value)` and applies it identically to either payload:

```python
assert decision != "ALLOW" or safe_predicate(payload)
```

Foreign-language probes run the real target subprocess with the raw string, raising `RuntimeError` for a non-zero exit or malformed output. The Python probe instead imports and calls `vulnapp.policy.allowed(payload)` directly so the kernel's Python coverage driver traces the actual policy source; it retains the same raw string and independently rendered invariant. The control succeeds because its value satisfies the invariant; an accepted exploit violates the invariant because of its value, never because of payload identity.

## Coverage and counting

There are **11 mechanism families × 5 exploit payload variants × 2 source revisions = 110 runnable revision-variants per language**. All seven languages therefore generate **385 Case directories** and **770 runnable revision-variants**.

A Case directory contains two revisions rather than two independently labelled findings. Counts are deliberately expressed as **runnable revision-variants**; they must not be described as 110 unique CVEs or a model-accuracy result. `catalog.json` records this rule.

| Family | Fixed-policy invariant independently checked by the probe | CWE |
| --- | --- | --- |
| `path-sibling-prefix` | Starts under `public/` and contains no `..` | CWE-22 |
| `authorization-missing-owner` | The two split requester/owner fields are equal | CWE-862 |
| `negative-amount` | Parsed amount is `0 <= amount <= 100` | CWE-20 |
| `integer-boundary` | Parsed integer is `0 <= amount <= 99` | CWE-190 |
| `url-hostname-suffix` | `urllib.parse.urlparse(value).hostname` exactly equals `api.example.test` | CWE-918 |
| `command-argument-validation` | Token matches `^[A-Za-z0-9_]+$`; no command is invoked | CWE-78 |
| `object-property-pollution` | Reserved prototype-like keys are denied | CWE-1321 |
| `header-crlf` | Header value contains neither CR nor LF | CWE-113 |
| `filename-extension-case` | Filename ends with final, lowercase `.pdf` | CWE-434 |
| `token-expiry-boundary` | Parsed expiry is strictly greater than the supplied current instant | CWE-613 |
| `redirect-absolute-network-path` | Starts with one local `/`, not `//` or a backslash path | CWE-601 |

## Framework fixtures and build replay

The generator includes executable project metadata **and makes the reference build script invoke the framework**, rather than merely planting a manifest:

| Language | Source fixture | Reference build command |
| --- | --- | --- |
| Python | `pyproject.toml` / installed setuptools | `python -c "import setuptools; ..." && python -m pip install --no-build-isolation --no-deps . && python -m compileall -q vulnapp` |
| JavaScript | npm package | `npm run build` |
| TypeScript | npm + pinned `@types/node` 22, TypeScript 5.7.3, Vite 6.0.11 | `npm install --ignore-scripts --no-audit --no-fund && npm run build` (`tsc && vite build`) |
| Java | Alternating Maven and Gradle cases | `mvn -q -DskipTests package` or `gradle --no-daemon classes`; Gradle targets Java 17 without requiring a JDK 17 toolchain |
| Ruby | Bundler and Rake | `bundle install --local --quiet && bundle exec rake build` (pinned image-installed gems) |
| Perl | `Makefile.PL`, Make, prove | `perl Makefile.PL >/dev/null && make >/dev/null && prove -l`; each test uses its family's benign control |
| C++ | Alternating CMake and Make cases | `cmake -S . -B build ... && cmake --build build ...` or `make all`; both use `--coverage -O0 -g` for gcov |

TypeScript sets `target: ES2022`, `sourceMap: true`, and `types: ["node"]`; its Vite entry imports the policy, so the actual web build includes it. Ruby represents CR and LF as escaped `"\r"` and `"\n"` literals in fixture source, not literal control newlines. The Python build checks that `setuptools` exists in the runtime image and disables build isolation/dependency resolution, avoiding unavailable build dependencies.

The fixtures intentionally have no production dependencies other than their named native build ecosystem. A runtime image missing a required tool reports **blocked**, never passed.

## CLI

```bash
# Generation only: writes a report saying execution was not requested; this is not a pass claim.
python tools/benchmark.py --root /tmp/corsair-polyglot --generate-only --output /tmp/polyglot-report.json

# Generate TypeScript cases and locally run one trusted fixture. This is explicitly NOT isolation.
python tools/benchmark.py --root /tmp/corsair-polyglot-ts --language typescript --limit 1 \
  --native-smoke --output /tmp/polyglot-native.json

# Replay selected trusted references through DockerSandboxes, with no model and no blind auditor.
python tools/benchmark.py --root /tmp/corsair-polyglot-docker --language python --limit 1 \
  --run-kernel --output /tmp/polyglot-docker.json
```

`--language` is repeatable and `--limit` bounds case directories selected for execution. `--workers N` bounds real concurrent Docker evaluations and preserves deterministic report order. `--native-smoke` runs generated trusted source on the host and labels every row `native-not-isolated`; it is a source/runtime smoke check, not a Corsair verdict. `--run-kernel` uses Docker sandboxes and trusted reference submissions, but configures no auditor and makes no model-accuracy claim. Native reports and per-case gate evidence are retained as content-addressed artifacts.

## Limitations

- The policies are compact, deterministic **synthetic regression templates**. They exercise representative invariants and build systems, not filesystem, network, shell, database, framework, or real-CVE side effects. In particular, the command-argument family validates a token and deliberately never invokes a malicious command.
- The fixture oracle says the trusted vulnerable/fixed pair should produce an exploitable/verified outcome. It is not a measurement of an LLM, an auditor, or a real-world CVE corpus.
- The shared probe is Python by design; delivered kernel-owned coverage adapters use coverage.py, c8/V8 source maps, JaCoCo, Devel::Cover, SimpleCov and gcov. Standard layouts are covered, not every possible project convention.
