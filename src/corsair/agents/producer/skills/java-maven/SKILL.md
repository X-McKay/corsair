---
name: java-maven
description: Build and cover Java targets with Maven and JaCoCo.
---
# Java / Maven runtime

- Image: JDK 21, Maven 3.9.11, Gradle 8.14.3, Python `pytest==9.0.3` / `coverage==7.13.4`, and pinned JaCoCo 0.8.13 agent and CLI. The build script may fetch dependencies while the build container has network; each probe is offline and must not download anything.
- The probe is still one Python module. Define `CONTROL_PAYLOAD`, `EXPLOIT_PAYLOAD`, and `run_target(payload)`; have it invoke the **already-built** Java program with `subprocess.run`, inspect its real result, and assert one invariant. Do not add Java tests or replace the target with a fake.
- Build a Maven project before probing, for example `mvn -B -DskipTests package`; for Gradle, use an available checked-in wrapper or `gradle build -x test`. Use the project’s normal command and keep generated output in its standard compile directory.
- Native coverage is JaCoCo, injected through `JAVA_TOOL_OPTIONS` by the kernel. It discovers `target/classes`, `build/classes/java/main`, `build/classes`, and `classes` recursively and maps reports only to an exact `src/main/java/...` path. Do not set or remove `JAVA_TOOL_OPTIONS`, write `/tmp/corsair`, or treat Python coverage as Java evidence.
- Set `target_file` to the exact repository-relative `.java` source path and choose executable lines in the reported method. A missing agent report, duplicate Java source path in a monorepo, a package/name mismatch, or zero JaCoCo instruction hits fails the coverage gate.
- Explore with `sed`, `grep`, and a short local build first. The sealed target tree is read-only during probes; use `tempfile` for input files and inherit the subprocess environment so the agent reaches the Java child process.
