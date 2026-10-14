---
name: control-probe
description: Write the benign control probe - ordinary input through the real seam, asserting ordinary behaviour.
---
# Benign control probe

The control shows that the test reaches the real target and that the target works on ordinary input. It must
stay true across any legitimate fix of the reported issue, so it never asserts the security property.

1. Read the cited source: the target, the seam the brief names, and how the target is loaded. Read one or two
   existing tests near it to learn the project's import or load path, fixtures and assertion style. If you
   cannot find how to load the real target, answer blocked; never copy the target into the test.
2. Prepare the state the call needs (files in a temporary directory, objects, configuration) before calling,
   so a setup failure cannot look like application behaviour.
3. Call the real target through the seam with the ordinary benign input the brief gives.
4. Assert the ordinary behaviour the brief states: a returned value, a specific exception, resulting state, or
   what a dependency double recorded. The assertion must be able to fail if the target misbehaves. Evaluate that
   condition once, write the `check` marker from it, then assert it with the run token as the failure message.
5. Do not assert a security guard, a rejection, a sanitised form or anything about adversarial input. Do not
   add a second test or an adversarial case.
6. Double only the dependencies the brief allows. A double may return canned values or record calls; it never
   replaces the target or the logic that produces the behaviour you assert.
7. Follow the probe-protocol skill for the markers and the token; they are the same as for the exploit probe.
8. Before answering drafted, re-read the whole file: the load path names the real production definition, the
   test name and file match the brief, every name is declared, `check` is computed from the asserted condition
   right before the assertion, the token appears only as that assertion's message, and the `start` and `end`
   markers are the first and last statements of the body.
