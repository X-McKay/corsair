---
name: probe-planning
description: How to choose a seam and write the control and exploit probe briefs.
---
# Planning two native probes

**Target and seam.** The target is the production function, method or handler where the reported condition is
decided. The seam is the narrowest public way a unit test can reach it: a direct call, a request through the
framework's own test client, or a constructor plus method. Prefer a seam that keeps the production logic
responsible for the property in the call path. Name the import or load path the test will use as it appears in
the source.

**Doubles.** Only dependencies may be doubled: databases, network clients, the filesystem, subprocesses, clocks.
Say which ones and what the double must record or return. Never double the target or the check under test.

**Control brief.** An ordinary, realistic input that a correct implementation handles successfully, and the
ordinary result to assert (a return value, a written record, a response). It must stay true after a legitimate
fix of the reported issue, so it must not assert anything about the security check itself.

**Exploit brief.** An adversarial input that would trigger the reported condition, and the safe property to
assert: the input is rejected, escaped, confined or has no effect on the doubled dependency. Phrase the
property as what safe code guarantees; the test fails when the code is vulnerable.

**Independence.** Write each brief as if the other did not exist: its own input, its own property, its own
citations. Do not refer to "the other test" or reuse the other input.

**Files and names.** Put each probe in its own new file under the given test directory, named so the framework
discovers it, with a test name valid in that framework (letters, digits and underscores, starting with a
letter or underscore).

**Citations.** Cite the target's definition, the seam and the line where the condition is decided. Quote a
short exact fragment of the cited lines; whitespace differences are tolerated, other differences are not.

**Refusing.** Use target_not_found when searching the tree finds no code matching the finding. Use
unsupported_scope when the property needs behaviour no unit seam can reach deterministically: a real external
service, database engine or network peer; wall-clock timing (timing side channels, regex backtracking or resource
exhaustion judged by duration or memory); a race between threads or processes; or deployment configuration.
