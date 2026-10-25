# Pilot threat model

The operator is trusted to authorize a finding and choose the source root, recipe, fixed arguments, runtime image, budgets and provider configuration. The model, its proposed payloads, and target source are untrusted. The Docker daemon, host kernel, package, driver and artifact store are trusted infrastructure.

The producer is limited to reading an immutable admitted source tar and submitting JSON payloads. It cannot modify source, assertions, trusted files, fixture policy, credentials or runtime permissions. The auditor is fresh-context and tool-free; neither source nor submit content can legitimately override its system instructions. All source paths are normalized below a configured root with symlink/special-file denial; tar materialization does not follow archive links.

Native target execution is offline and nonprivileged. Read-only source/driver/fixtures and no-new-privileges/capability/resource limits prevent ordinary workspace/policy changes. These controls do not make Docker a universal isolation boundary: a compromised kernel/runtime or malicious in-process interpreter behavior is outside pilot qualification. Use a dedicated VM and a separately qualified stronger runtime for hostile workloads.

The driver distinguishes actual returned private-fixture disclosure from failed control behavior, expected rejection, unexpected exceptions, missing native results and unrelated assertions. The parent checks source/submission/image/operation/role identity, Docker/native exit consistency, native result counts, source coverage and cleanup. A native failing test alone never proves the reported security violation. In-process observer records can still be attacked by arbitrary hostile target code; this threat requires stronger independent observation, not a model verdict.

Random fixture contents are not model-visible. Known oracle/sensitive filenames are denied during source admission, while evaluator truth never enters workflow inputs. Arbitrary embedded credentials in source are not guaranteed to be detected: the operator must sanitize the admitted tree. Worker credentials do not enter containers.

Correlated producer/auditor mistakes, malicious prompt injection, harness-aware target behavior, artifact-host loss, insufficient whole-application context and blocked provider behavior remain explicit risks. No fabricated negative clearance, universal patch proof, exactly-once side effect or automatic publication is authorized.
