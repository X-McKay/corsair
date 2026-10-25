---
name: source-grounding
description: Derive one declarative Corsair producer payload pair from an admitted finding packet and source snapshot. Use when grounding a producer proposal in the configured callable, payload parameter, public fixtures, and source transformations.
---

# Source grounding

1. Read the exact finding file only when needed, using the already provided bounded source readers.
2. Map the production callable, `payload_parameter`, fixed operator arguments, declared public fixture paths, and the source transformations from the controlled parameter to the reported mechanism.
3. Distinguish a payload value from a mapping of keyword arguments. Supply only the value for `payload_parameter`; do not alter fixed arguments or fixture selection.
4. Derive valid benign and path inputs from the source and operator-declared fixture paths. Respect the callable's actual path handling and transformations rather than inventing normalization or directories.
5. Select one payload pair whose candidate implements the stated hypothesis. Keep the hypothesis tied to the observed source mechanism.
6. Copy the revision and parent values from the packet into the plan exactly. Do not manufacture workflow history.
7. Return `no_grounded_candidate` with a concise reason when the packet and admissible source cannot ground a valid pair. Do not guess a candidate.
