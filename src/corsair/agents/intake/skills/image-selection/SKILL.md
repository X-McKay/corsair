---
name: image-selection
description: Use when an intake issue needs a test image, available candidates differ in capabilities, or missing requirements and unknown compatibility must be distinguished.
---

# Selecting an available image

The agent interprets the issue and chooses an image. The comparison tool supplies reviewed
inventory facts; it does not establish issue scope, source grounding or exploitability.

1. Establish one reported issue and inspect its relevant source. Identify the narrowest
   execution mode and necessary capability categories. Missing issue context or unresolved
   multiple findings needs input before recommending an image.
2. Call `compare_images` with that language, execution mode and requirement list. An empty
   list means no extra capability is needed; unknown means a concrete fact remains unresolved.
3. Read each candidate's matches and missing requirements. A compatible row supports an
   exact inventory reference. A scanner-supplied tag is not an inventory entry. No candidate
   can authorize network or privileged execution, even if its metadata lists that capability.
4. For edge cases, inspect the actual source/imports/manifests and refine the profile if
   justified. A direct component check may need less infrastructure than a whole application;
   retain the reported behavior and scope when choosing that boundary. Never delete a genuine
   dependency or service requirement merely to make an image fit. Compare again within budget.
5. Choose an exact compatible reference when the issue and grounding are resolved. Do not
   withhold it merely because the scanner report does not name an image. If no candidate fits,
   return null and NO_COMPATIBLE_IMAGE with known requirement categories. If an essential fact
   is unresolved, return null and IMAGE_UNDETERMINED/REQUIREMENTS_UNRESOLVED as appropriate.

| Observation | Response |
| --- | --- |
| Standard-library callable; no extra capabilities | Compare callable with requirements `[]`. |
| Callable image but actual endpoint requires server startup | Keep service requirements; do not infer HTTP support. |
| Candidate has reviewed extra capabilities | Use its metadata; a recipe name is unnecessary. |
| Requirement/capability is not established | Inspect source or retain uncertainty; do not guess installed packages. |

The tool is bounded in-memory comparison against this episode's available inventory. It cannot
pull/build images, execute commands, install packages or discover registries. Tool errors and
output limits are explicit; absence of a complete comparison is not proof that no image exists.
Native skill refresh tools load this packaged instruction text only, without additional powers.
