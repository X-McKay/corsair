---
name: junit4
description: Write one Corsair probe as a single JUnit 4 test method run by Maven, with the start and end markers and the run token.
---
# JUnit 4 probe (Maven)

**File and name.** Put the class under `src/test/java/`, in the package directory of the code under test (for
`com.example.Parser`, `src/test/java/com/example/<Class>Test.java`, declaring `package com.example;`). The class
is `public`, its name is the file name without `.java`, and it holds exactly one `public void` method annotated
`@org.junit.Test`, named as planned; it is run alone with `-Dtest=<Class>#<method>`. Use only test dependencies the
project's `pom.xml` already declares; the run is offline. Write source for the project's `maven.compiler.source`
level: below 1.8 there are no lambdas, and below 10 there is no `var`.

**Markers.** The environment variable `CORSAIR_MARKER_DIR` names a directory. The first statement of the method
writes a file named `start` there; the last statement, after every assertion, writes `end`:

```java
@Test
public void name() throws Exception {
    new java.io.FileOutputStream(new java.io.File(System.getenv("CORSAIR_MARKER_DIR"), "start")).close();
    Result result = target.call(input);
    assertTrue(System.getenv("CORSAIR_TOKEN"), propertyHolds(result));   // security probe only
    new java.io.FileOutputStream(new java.io.File(System.getenv("CORSAIR_MARKER_DIR"), "end")).close();
}
```

**Token.** In the security (exploit) probe, the security assertion's message is exactly
`System.getenv("CORSAIR_TOKEN")`. JUnit 4 puts the message first: `assertTrue(message, condition)`. Never print
the token elsewhere. The control probe asserts with no token.

**Pitfalls.** Do not catch `AssertionError`/`Throwable` around the assertion; do not use `@Ignore`, `Assume` or
`@Test(expected = AssertionError.class)`; keep exactly one `@Test` method in the class.
