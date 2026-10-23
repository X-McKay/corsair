# Runtime selection

Inspect the reported file and the closest build manifest first. The operator's matrix supplies the image and native coverage collector; do not choose or weaken verification policy in the probe. All languages use one Python `run_target(payload)` driver. Load the matching build guide only when needed.

Use the project's existing wrapper and lockfile: Python `uv sync --frozen`, pip/setuptools or Poetry; Java `./mvnw`/Maven or `./gradlew`; Node `npm ci`, pnpm or yarn, then the package's build script; Ruby `bundle install` and Rake; Perl MakeMaker, Module::Build or cpanm; C++ CMake/Ninja or Make with GCC `--coverage`. Match declared language/toolchain versions rather than force an incompatible image. If the supplied image lacks a required toolchain, report that dependency instead of silently switching runtimes.

Replay every prerequisite in `build_script`. Probe containers are offline, unprivileged and start from the same compiled image. Write temporary fixtures/results under `/tmp`, not the frozen repository. Do not fetch dependencies, rebuild the target or start external network services during probing. Loopback services inside one offline twin are permissible when the real framework needs them; wait for readiness and stop them before returning.

For foreign targets, invoke subprocess argument lists and preserve the inherited environment so c8, JaCoCo, SimpleCov, Devel::Cover or gcov can record target execution. TypeScript builds must emit source maps. Java classes need debug line numbers. C++ builds need matching `.gcno` files and writable redirected `.gcda` output. Never substitute log markers or wrapper coverage for native target-line evidence.
