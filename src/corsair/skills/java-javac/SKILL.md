---
name: java-javac
description: Write Java 21 differential probes compiled with javac and measured with JaCoCo. Use when the runtime is java / javac-java.
---

# Java / javac

Submit one public class named `CorsairProbe`:

```java
public final class CorsairProbe {
    public static final String CONTROL_PAYLOAD = "benign";
    public static final String EXPLOIT_PAYLOAD = "malicious";

    public static boolean runTarget(String payload) throws Exception {
        Result result = Target.operation(payload);
        return result.isSafe();
    }
}
```

- Return one boolean security invariant for both payloads. `true` means it held; `false` means the reported condition
  occurred. The kernel-owned driver performs the assertion. Every thrown application or probe exception is an error.
- Call the real target through its public API. Do not use Mockito, PowerMock, EasyMock, bytecode agents, reflection
  to replace behavior, or a hand-written copy of the target.
- Put compiled project classes in `/work/.corsair-java/classes` in the build script. Put optional dependency jars
  in `/work/.corsair-java/lib`. For the smallest source tree:

  ```bash
  mkdir -p /work/.corsair-java/classes
  javac -d /work/.corsair-java/classes /work/path/to/Target.java
  ```

- Maven and Gradle are supported when the checked-in project defines them: run the locked/offline-capable build,
  then copy its compiled main classes and required jars into those two directories. Do not download an ad hoc test
  framework; the runtime supplies the driver and JaCoCo.
- Use `Files.createTempDirectory` for fixtures and remove known files in `finally`. The source tree is read-only and
  the probe has no network.
- Java source identity uses the declared package and basename because JaCoCo omits source roots. If two modules map
  to the same identity, coverage is rejected as ambiguous instead of being credited to either file.
