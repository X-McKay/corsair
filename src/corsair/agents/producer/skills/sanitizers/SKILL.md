---
name: sanitizers
description: Use sanitizer diagnostics without weakening coverage evidence.
---
# Sanitizers and failure evidence

A nonzero subprocess exit is not itself a security proof. In the shared Python driver, capture the real target result and assert the hypothesized security invariant. For a memory-safety finding, assert the absence of the specific sanitizer diagnostic and verify that the exploit genuinely reached the target through native coverage. A missing executable, malformed input type, timeout, unrelated assertion or generic crash must not become an invariant violation.

Compile C++ targets with GCC `--coverage -O0 -g`; add `-fsanitize=address,undefined -fno-omit-frame-pointer` for the relevant memory or arithmetic class. Set sanitizer options equally for both payloads. Prefer recoverable UBSan diagnostics when they preserve gcov evidence; a fatal ASan abort may prevent coverage flushing, and missing target coverage must remain inconclusive. Never disable the coverage gate to accommodate a crash.

For Python and dynamic-language targets, use their real public seam and a specific state/result assertion. Treat expected validation exceptions on the fixed revision as rejection behavior, and let the invariant decide whether protected state changed. Keep benign and malicious payloads the same accepted public type. Catch only the expected exception class, never blanket exceptions to fabricate a passing control.
