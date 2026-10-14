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

**Exploit brief.** The exploit probe is a proof-of-vulnerability (PoV) test. Give an adversarial input that would
trigger the reported condition, and the observable condition to assert as occurring: for example the injected
command reached the subprocess double, the resolved path is outside the base directory, the query sent to the
database double carries the input as structure, the response holds the unescaped markup. Phrase the property as
what happens when the issue is real; the test passes when the code is vulnerable and fails when it is not. The
condition must be one a correct implementation would not show, so the assertion can fail.

**Independence.** Write each brief as if the other did not exist: its own input, its own property, its own
citations. Do not refer to "the other test" or reuse the other input.

**Files and names.** Put each probe in its own new file under the given test directory, named so the framework
discovers it, with a test name valid in that framework (letters, digits and underscores, starting with a
letter or underscore).

**Citations.** Cite the target's definition, the seam and the line where the condition is decided. Quote a
short exact fragment of the cited lines; whitespace differences are tolerated, other differences are not.

**Refusing.** Use target_not_found when searching the tree finds no code matching the finding. Scope is
provability, not category: plan any finding both probes can prove inside the workspace, deterministically and with no
outbound network, using local stand-ins where needed (a local server, a temporary file, an in-process double of a
dependency). Use unsupported_scope, and say what is missing, only when the proof needs something the workspace cannot
supply: a real remote endpoint, the host trust store, a system-wide cipher policy, or a specific library build.