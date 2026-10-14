---
name: junit5
description: Write one Corsair probe as a single JUnit 5 (Jupiter) test method run by Maven, with the start, check and end markers and the run token.
---
# JUnit 5 probe (Maven)

**File and name.** Put the class under `src/test/java/`, in the package directory of the code under test (for
`com.example.UserDao`, `src/test/java/com/example/<Class>Test.java`, declaring `package com.example;`). The class
name is the file name without `.java`. It holds exactly one `@Test` method named as planned; it is run alone with
`-Dtest=<Class>#<method>`. `@ParameterizedTest` on that one method is allowed instead of `@Test`. Use only test
dependencies the project's `pom.xml` already declares; the run is offline.

**Markers.** The environment variable `CORSAIR_MARKER_DIR` names a directory. The first statement of the method
writes a file named `start` there. Immediately before the main assertion it writes `check`, containing `holds` if
the asserted condition holds and `violated` if not, computed from the same variable the assertion checks. The last
statement, after every assertion, writes `end`:

```java
@Test
void name() throws Exception {
    java.nio.file.Files.write(java.nio.file.Paths.get(System.getenv("CORSAIR_MARKER_DIR"), "start"), new byte[0]);
    Result result = target.call(input);
    boolean holds = propertyHolds(result);
    java.nio.file.Files.write(java.nio.file.Paths.get(System.getenv("CORSAIR_MARKER_DIR"), "check"),
            (holds ? "holds" : "violated").getBytes(java.nio.charset.StandardCharsets.UTF_8));
    assertTrue(holds, System.getenv("CORSAIR_TOKEN"));
    java.nio.file.Files.write(java.nio.file.Paths.get(System.getenv("CORSAIR_MARKER_DIR"), "end"), new byte[0]);
}
```

**Token.** In both probes, the main assertion's message is exactly `System.getenv("CORSAIR_TOKEN")` (Jupiter puts
the message last: `assertTrue(condition, message)`). Never print the token elsewhere.

**Pitfalls.** Do not catch `AssertionError`/`Throwable` around the assertion; do not use `@Disabled`,
`assumeTrue` or `assertThrows(AssertionError.class, ...)`; the source must compile for the project's
`maven.compiler` level; keep exactly one test method in the class.
