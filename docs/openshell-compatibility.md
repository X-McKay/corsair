# OpenShell runtime compatibility

Corsair's OpenShell adapter is a real governed-execution integration with OpenShell v0.1.5's local Docker driver. It is not a claim that every upstream toolchain is compatible with that runtime. Docker remains the default and supports the existing seven-language twin corpus.

## Verified behavior

Live gateway tests completed full Python vulnerable/fixed replay: four fresh offline runs, target coverage, `LIKELY_EXPLOITABLE`, `Fix.VERIFIED` and confirmed cleanup. A JavaScript trusted twin also passed. Separate live checks rejected a root workload policy and showed that a uid-1000 probe cannot rewrite uid-1001 sealed source or open an unapproved network connection. The exact final regression counts are recorded in [provider integration validation](provider-integrations.md).

## Make-based builds

The installed Debian GNU Make 4.3 refused ordinary recipes inside non-root OpenShell execution with `Operation not permitted`, even though direct shell commands worked. The upstream issue attributes this to denied identity-reset syscalls: Make attempts `setresuid`/`setresgid` without changing its identity, but the sandbox seccomp filter rejects those calls.[1] This is not resolved by broader Landlock filesystem access, and Corsair does not relax seccomp, identity isolation or source immutability.

The upstream thread reports GNU Make 4.4.1 as a safe in-image workaround, including on aarch64. That specific toolchain upgrade has **not** been validated in Corsair's current runtime images. The proposed OpenShell filter fix is still open as of this investigation.[1] [2] Until a compatible runtime/image is deliberately selected and tested, Make-based Perl and CMake/Make C++ builds on this backend remain unsupported in the tested configuration. Use the existing Docker backend for those projects. No fallback is performed automatically.

## Registry access and Ruby

The first TypeScript/npm and Java/Maven OpenShell attempts failed because their required registries were not in the operator-reviewed egress policy. Configure exact endpoint and executable identities for dependencies that the project legitimately needs, then rerun the complete twin; the adapter never auto-approves a registry. The illustrative [build policy](../config/openshell-build-policy.example.yaml) is intentionally not production-ready or enabled automatically.

The initial Ruby/Bundler twin errored during control execution under OpenShell's non-root environment. A successful Bundler twin on this backend is not claimed. These failures are retained as failed evidence, not counted as passes. Existing Docker Ruby/Bundler tests remain separate.

## References

[1]: https://github.com/NVIDIA/OpenShell/issues/4102 "OpenShell GNU Make identity-reset execution failure and reported Make 4.4.1 workaround"
[2]: https://github.com/NVIDIA/OpenShell/pull/4104 "Open proposed identity-preserving seccomp fix"
