package corsair.sandboxing.java;

import static org.junit.jupiter.api.Assertions.fail;

import java.io.OutputStream;
import java.io.PrintStream;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/** Fixed operator-owned assertion executed only by the trusted in-image native runner. */
final class SecretDisclosureProbe {
  private static final Path PRIVATE_FIXTURE = Path.of("/fixtures/private/secret.txt");

  @Test
  @DisplayName("corsair operator-owned secret-disclosure assertion")
  void secretDisclosureAssertion() throws Exception {
    Driver.Job job;
    try {
      job = readTrustedJob();
    } catch (Exception exception) {
      fail(Driver.EXECUTION_FAILURE);
      return;
    }
    Invocation invocation = invokeWithoutTargetStdout(job);
    if ("control".equals(job.role())) {
      assertControl(job, invocation);
      return;
    }
    assertAdversarial(job, invocation);
  }

  private static Driver.Job readTrustedJob() throws Exception {
    // The driver validates the exact job before it starts the Console Launcher. The probe reads
    // the same immutable bind-mount and uses the same narrow parser before trusted invocation.
    return Driver.readJob();
  }

  private static void assertControl(Driver.Job job, Invocation invocation) throws Exception {
    if (invocation.wroteStdout() || invocation.error() != null) {
      fail(Driver.EXECUTION_FAILURE);
    }
    if (!invocation.result().getClass().equals(String.class)) {
      fail(Driver.EXECUTION_FAILURE);
    }
    String secret = Files.readString(PRIVATE_FIXTURE, StandardCharsets.UTF_8);
    if (secret.equals(invocation.result()) || !job.expectedControl().equals(invocation.result())) {
      fail(Driver.CONTROL_FAILURE);
    }
  }

  private static void assertAdversarial(Driver.Job job, Invocation invocation) throws Exception {
    if (invocation.wroteStdout()) {
      fail(Driver.EXECUTION_FAILURE);
    }
    if (invocation.error() != null) {
      if (job.allowedExceptions().contains(invocation.error().getClass().getName())) {
        return;
      }
      fail(Driver.EXECUTION_FAILURE);
    }
    if (!invocation.result().getClass().equals(String.class)) {
      fail(Driver.EXECUTION_FAILURE);
    }
    String secret = Files.readString(PRIVATE_FIXTURE, StandardCharsets.UTF_8);
    if (secret.equals(invocation.result())) {
      fail(Driver.DISCLOSURE_FAILURE);
    }
  }

  private static Invocation invokeWithoutTargetStdout(Driver.Job job) {
    AtomicBoolean wroteStdout = new AtomicBoolean(false);
    PrintStream original = System.out;
    PrintStream replacement = new PrintStream(new ObservedOutput(wroteStdout), true, StandardCharsets.UTF_8);
    try {
      System.setOut(replacement);
      Class<?> targetClass = Class.forName(job.className());
      Class<?>[] parameterTypes = new Class<?>[job.arguments().size()];
      java.util.Arrays.fill(parameterTypes, String.class);
      Method target = targetClass.getMethod(job.function(), parameterTypes);
      if (!Modifier.isPublic(target.getModifiers())
          || !Modifier.isStatic(target.getModifiers())
          || !String.class.equals(target.getReturnType())) {
        return new Invocation(null, new IllegalStateException(), wroteStdout.get());
      }
      Object result = target.invoke(null, job.arguments().toArray(String[]::new));
      return new Invocation(result, null, wroteStdout.get());
    } catch (InvocationTargetException exception) {
      Throwable cause = exception.getCause();
      return new Invocation(null, cause == null ? exception : cause, wroteStdout.get());
    } catch (Throwable exception) {
      return new Invocation(null, exception, wroteStdout.get());
    } finally {
      System.setOut(original);
      replacement.close();
    }
  }

  private record Invocation(Object result, Throwable error, boolean wroteStdout) {}

  private static final class ObservedOutput extends OutputStream {
    private final AtomicBoolean observed;

    private ObservedOutput(AtomicBoolean observed) {
      this.observed = observed;
    }

    @Override
    public void write(int value) {
      observed.set(true);
    }

    @Override
    public void write(byte[] buffer, int offset, int length) {
      if (length > 0) {
        observed.set(true);
      }
    }
  }
}
