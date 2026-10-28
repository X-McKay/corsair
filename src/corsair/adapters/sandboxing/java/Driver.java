package corsair.sandboxing.java;

import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.Node;
import org.w3c.dom.NodeList;

/**
 * Trusted, in-image Java observer for the fixed static-String disclosure recipe.
 *
 * <p>The operator writes a JSON-only job. This driver validates it before compiling the one
 * admitted source file with the JDK, invokes a checked-in JUnit assertion through the native
 * Console Launcher, projects JUnit/JaCoCo output into one safe record, and never copies a target
 * diagnostic or fixture value to stdout. The constrained container remains the execution boundary;
 * this code does not claim hostile-JVM integrity.
 */
public final class Driver {
  static final String JOB_PATH = "/input/job.json";
  static final Path WORK = Path.of("/work");
  static final Path CLASSES = WORK.resolve("classes");
  static final Path JUNIT_DIR = WORK.resolve("junit");
  static final Path JACOCO_EXEC = WORK.resolve("jacoco.exec");
  static final Path JACOCO_XML = WORK.resolve("jacoco.xml");
  static final Path LIBRARY = Path.of("/opt/corsair/lib");
  static final Path TRUSTED_CLASSES = Path.of("/opt/corsair/classes");
  static final String SCHEMA_VERSION = "corsair.driver/1";
  static final String JOB_SCHEMA_VERSION = "corsair.driver-job/1";
  static final String PROBE_CLASS = "corsair.sandboxing.java.SecretDisclosureProbe";
  static final String CONTROL_FAILURE = "corsair control return did not match the public expectation";
  static final String DISCLOSURE_FAILURE = "corsair adversarial returned the private fixture";
  static final String EXECUTION_FAILURE = "corsair target threw an unallowed exception";
  private static final int REPORT_LIMIT = 32 * 1024;
  private static final int PARSED_REPORT_LIMIT = 1024 * 1024;
  private static final int JOB_LIMIT = 64 * 1024;
  private static final ObjectMapper JSON = new ObjectMapper(new JsonFactory());

  private Driver() {}

  public static void main(String[] arguments) {
    int exitCode;
    try {
      Job job = readJob();
      exitCode = run(job);
    } catch (InvalidJobException | IOException exception) {
      writeRecord(invalidRecord());
      exitCode = 2;
    } catch (RuntimeException exception) {
      // Do not turn unexpected trusted-driver diagnostics into output that may carry target data.
      writeRecord(invalidRecord());
      exitCode = 2;
    }
    System.exit(exitCode);
  }

  private static int run(Job job) {
    int compileExit = compileTarget(job);
    if (compileExit != 0) {
      writeRecord(recordFor(job, compileExit, Report.invalid(), List.of(), Map.of()));
      return compileExit;
    }

    int nativeExit = runJunit(job);
    boolean coverageGenerated = writeCoverage();
    Report report = readJunit();
    List<Integer> coveredLines = coverageGenerated ? coveredLines(job) : List.of();
    writeRecord(recordFor(job, nativeExit, report, coveredLines, nativeReports()));
    return nativeExit;
  }

  static Job readJob() throws IOException, InvalidJobException {
    Path path = Path.of(JOB_PATH);
    if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS) || Files.size(path) > JOB_LIMIT) {
      throw new InvalidJobException();
    }
    JsonNode root;
    try (InputStream stream = Files.newInputStream(path, StandardOpenOption.READ);
        JsonParser parser = JSON.getFactory().createParser(stream)) {
      root = JSON.readTree(parser);
      if (parser.nextToken() != null) {
        throw new InvalidJobException();
      }
    }
    return Job.from(root);
  }

  private static int compileTarget(Job job) {
    try {
      Files.createDirectories(CLASSES);
      Process process =
          new ProcessBuilder(
                  javaTool("javac"),
                  "-proc:none",
                  "-g",
                  "-d",
                  CLASSES.toString(),
                  "/source/" + job.moduleFile())
              .directory(WORK.toFile())
              .redirectInput(ProcessBuilder.Redirect.from(Path.of("/dev/null").toFile()))
              .redirectOutput(ProcessBuilder.Redirect.DISCARD)
              .redirectError(ProcessBuilder.Redirect.DISCARD)
              .start();
      return process.waitFor();
    } catch (IOException exception) {
      return 2;
    } catch (InterruptedException exception) {
      Thread.currentThread().interrupt();
      return 2;
    }
  }

  private static int runJunit(Job job) {
    try {
      Files.createDirectories(JUNIT_DIR);
      String classpath = String.join(System.getProperty("path.separator"),
          CLASSES.toString(), TRUSTED_CLASSES.toString(),
          LIBRARY.resolve("jackson-annotations.jar").toString(),
          LIBRARY.resolve("jackson-core.jar").toString(),
          LIBRARY.resolve("jackson-databind.jar").toString());
      String coverageIncludes = job.className().replace('.', '/') + "*";
      Process process =
          new ProcessBuilder(
                  javaTool("java"),
                  "-javaagent:"
                      + LIBRARY.resolve("jacocoagent.jar")
                      + "=destfile="
                      + JACOCO_EXEC
                      + ",append=false,output=file,dumponexit=true,includes="
                      + coverageIncludes,
                  "-jar",
                  LIBRARY.resolve("junit-platform-console-standalone.jar").toString(),
                  "execute",
                  "--class-path",
                  classpath,
                  "--select-class",
                  PROBE_CLASS,
                  "--reports-dir",
                  JUNIT_DIR.toString(),
                  "--disable-banner",
                  "--details=none")
              .directory(WORK.toFile())
              .redirectInput(ProcessBuilder.Redirect.from(Path.of("/dev/null").toFile()))
              .redirectOutput(ProcessBuilder.Redirect.DISCARD)
              .redirectError(ProcessBuilder.Redirect.DISCARD)
              .start();
      return process.waitFor();
    } catch (IOException exception) {
      return 2;
    } catch (InterruptedException exception) {
      Thread.currentThread().interrupt();
      return 2;
    }
  }

  private static boolean writeCoverage() {
    if (!Files.isRegularFile(JACOCO_EXEC, LinkOption.NOFOLLOW_LINKS)) {
      return false;
    }
    try {
      Process process =
          new ProcessBuilder(
                  javaTool("java"),
                  "-jar",
                  LIBRARY.resolve("jacococli.jar").toString(),
                  "report",
                  JACOCO_EXEC.toString(),
                  "--classfiles",
                  CLASSES.toString(),
                  "--sourcefiles",
                  "/source",
                  "--xml",
                  JACOCO_XML.toString(),
                  "--quiet")
              .directory(WORK.toFile())
              .redirectInput(ProcessBuilder.Redirect.from(Path.of("/dev/null").toFile()))
              .redirectOutput(ProcessBuilder.Redirect.DISCARD)
              .redirectError(ProcessBuilder.Redirect.DISCARD)
              .start();
      return process.waitFor() == 0 && Files.isRegularFile(JACOCO_XML, LinkOption.NOFOLLOW_LINKS);
    } catch (IOException exception) {
      return false;
    } catch (InterruptedException exception) {
      Thread.currentThread().interrupt();
      return false;
    }
  }

  private static String javaTool(String name) {
    return Path.of(System.getProperty("java.home"), "bin", name).toString();
  }

  private static Report readJunit() {
    try {
      Path report = singleReport();
      if (!Files.isRegularFile(report, LinkOption.NOFOLLOW_LINKS)
          || Files.size(report) > PARSED_REPORT_LIMIT) {
        return Report.invalid();
      }
      Document document = secureDocument(report);
      NodeList cases = document.getElementsByTagName("testcase");
      if (cases.getLength() != 1 || !(cases.item(0) instanceof Element testCase)) {
        return Report.invalid();
      }
      if (!"secretDisclosureAssertion()".equals(testCase.getAttribute("name"))
          || !PROBE_CLASS.equals(testCase.getAttribute("classname"))) {
        return Report.invalid();
      }
      int failures = descendants(testCase, "failure");
      int errors = descendants(testCase, "error");
      int skipped = descendants(testCase, "skipped");
      if (failures + errors + skipped > 1) {
        return Report.invalid();
      }
      String status = failures > 0 ? "FAILURE" : errors > 0 ? "ERROR" : skipped > 0 ? "SKIPPED" : "PASS";
      return new Report(true, status, 1, failures, errors, skipped, testCase);
    } catch (Exception exception) {
      return Report.invalid();
    }
  }

  private static List<Integer> coveredLines(Job job) {
    try {
      if (Files.size(JACOCO_XML) > PARSED_REPORT_LIMIT) {
        return List.of();
      }
      Document document = secureDocument(JACOCO_XML);
      String targetClass = job.className().replace('.', '/');
      Element target = null;
      NodeList classes = document.getElementsByTagName("class");
      for (int index = 0; index < classes.getLength(); index++) {
        if (classes.item(index) instanceof Element candidate
            && targetClass.equals(candidate.getAttribute("name"))) {
          target = candidate;
          break;
        }
      }
      if (target == null || !job.moduleFile().endsWith(target.getAttribute("sourcefilename"))) {
        return List.of();
      }
      Node parent = target.getParentNode();
      if (!(parent instanceof Element packageElement)
          || !"package".equals(packageElement.getTagName())) {
        return List.of();
      }
      Element source = null;
      NodeList sources = packageElement.getElementsByTagName("sourcefile");
      for (int index = 0; index < sources.getLength(); index++) {
        if (sources.item(index) instanceof Element candidate
            && target.getAttribute("sourcefilename").equals(candidate.getAttribute("name"))) {
          source = candidate;
          break;
        }
      }
      if (source == null) {
        return List.of();
      }
      Set<Integer> lines = new HashSet<>();
      NodeList lineNodes = source.getElementsByTagName("line");
      for (int index = 0; index < lineNodes.getLength(); index++) {
        if (!(lineNodes.item(index) instanceof Element line)) {
          return List.of();
        }
        int number = positive(line.getAttribute("nr"));
        int coveredInstructions = nonnegative(line.getAttribute("ci"));
        if (number < 1 || coveredInstructions < 0) {
          return List.of();
        }
        if (coveredInstructions > 0) {
          lines.add(number);
        }
      }
      return lines.stream().sorted().toList();
    } catch (Exception exception) {
      return List.of();
    }
  }

  private static Document secureDocument(Path report) throws Exception {
    DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
    factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
    // JaCoCo declares its report DTD. Accept that declaration but never load any external content.
    factory.setFeature("http://apache.org/xml/features/nonvalidating/load-external-dtd", false);
    factory.setFeature("http://xml.org/sax/features/external-general-entities", false);
    factory.setFeature("http://xml.org/sax/features/external-parameter-entities", false);
    factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_DTD, "");
    factory.setAttribute(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
    factory.setXIncludeAware(false);
    factory.setExpandEntityReferences(false);
    return factory.newDocumentBuilder().parse(report.toFile());
  }

  private static int descendants(Element element, String tagName) {
    return element.getElementsByTagName(tagName).getLength();
  }

  private static int positive(String value) {
    try {
      int parsed = Integer.parseInt(value);
      return parsed > 0 ? parsed : -1;
    } catch (NumberFormatException exception) {
      return -1;
    }
  }

  private static int nonnegative(String value) {
    try {
      int parsed = Integer.parseInt(value);
      return parsed >= 0 ? parsed : -1;
    } catch (NumberFormatException exception) {
      return -1;
    }
  }

  private static Map<String, Object> recordFor(
      Job job,
      int exitCode,
      Report report,
      List<Integer> coveredLines,
      Map<String, String> nativeReports) {
    String outcome = "ERROR";
    String observationKind = "execution_error";
    boolean targetExecuted = false;
    String junitStatus = report.status();
    if (report.valid() && !coveredLines.isEmpty()) {
      if ("PASS".equals(report.status())) {
        outcome = "PROPERTY_HELD";
        observationKind = "held";
        targetExecuted = true;
      } else if ("control".equals(job.role()) && report.hasMarker(CONTROL_FAILURE)) {
        outcome = "INVALID";
        observationKind = "invalid_control";
        targetExecuted = true;
        junitStatus = "INVALID";
      } else if ("adversarial".equals(job.role()) && report.hasMarker(DISCLOSURE_FAILURE)) {
        outcome = "VIOLATION";
        observationKind = "disclosure";
        targetExecuted = true;
      } else {
        junitStatus = "ERROR";
      }
    } else {
      junitStatus = "ERROR";
    }
    Map<String, Object> junit = new HashMap<>();
    junit.put("status", junitStatus);
    junit.put("tests", report.tests());
    junit.put("failures", report.failures());
    junit.put("errors", report.errors());
    junit.put("skipped", report.skipped());
    Map<String, Object> record = baseRecord(job.operationId(), job.role(), job.sourceDigest(), job.submissionDigest());
    record.put("native_exit_code", exitCode);
    record.put("outcome", outcome);
    record.put("observation_kind", observationKind);
    record.put("target_executed", targetExecuted);
    record.put("covered_lines", coveredLines);
    record.put("coverage_file", job.moduleFile());
    record.put("junit", junit);
    record.put("native_reports", nativeReports);
    return record;
  }

  private static Map<String, Object> invalidRecord() {
    Map<String, Object> junit = new HashMap<>();
    junit.put("status", "INVALID");
    junit.put("tests", 0);
    junit.put("failures", 0);
    junit.put("errors", 0);
    junit.put("skipped", 0);
    Map<String, Object> record = baseRecord("", "", "", "");
    record.put("native_exit_code", 2);
    record.put("outcome", "INVALID");
    record.put("observation_kind", "execution_error");
    record.put("target_executed", false);
    record.put("covered_lines", List.of());
    record.put("coverage_file", "");
    record.put("junit", junit);
    return record;
  }

  private static Map<String, Object> baseRecord(
      String operationId, String role, String sourceDigest, String submissionDigest) {
    Map<String, Object> record = new HashMap<>();
    record.put("schema_version", SCHEMA_VERSION);
    record.put("operation_id", operationId);
    record.put("role", role);
    record.put("source_digest", sourceDigest);
    record.put("submission_digest", submissionDigest);
    return record;
  }

  private static Map<String, String> nativeReports() {
    Map<String, String> reports = new HashMap<>();
    readBoundedReport(singleReport(), reports, "junit");
    readBoundedReport(JACOCO_XML, reports, "coverage");
    return reports;
  }

  private static Path singleReport() {
    // JUnit emits separate engine reports; only the selected Jupiter assertion owns this recipe.
    return JUNIT_DIR.resolve("TEST-junit-jupiter.xml");
  }

  private static void readBoundedReport(Path path, Map<String, String> reports, String name) {
    try {
      if (Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS) && Files.size(path) <= REPORT_LIMIT) {
        reports.put(name, Files.readString(path, StandardCharsets.UTF_8));
      }
    } catch (IOException exception) {
      // A missing/invalid report is represented by the projected ERROR receipt, not a diagnostic.
    }
  }

  private static void writeRecord(Map<String, Object> record) {
    try {
      JSON.writeValue(System.out, record);
      System.out.write('\n');
      System.out.flush();
    } catch (IOException exception) {
      // No second stdout record is safe if stdout itself failed.
    }
  }

  static final class Job {
    private final String operationId;
    private final String role;
    private final String sourceDigest;
    private final String submissionDigest;
    private final String moduleFile;
    private final String className;
    private final String function;
    private final List<String> arguments;
    private final String expectedControl;
    private final Set<String> allowedExceptions;
    private final String payload;

    private Job(
        String operationId,
        String role,
        String sourceDigest,
        String submissionDigest,
        String moduleFile,
        String className,
        String function,
        List<String> arguments,
        String expectedControl,
        Set<String> allowedExceptions,
        String payload) {
      this.operationId = operationId;
      this.role = role;
      this.sourceDigest = sourceDigest;
      this.submissionDigest = submissionDigest;
      this.moduleFile = moduleFile;
      this.className = className;
      this.function = function;
      this.arguments = List.copyOf(arguments);
      this.expectedControl = expectedControl;
      this.allowedExceptions = Set.copyOf(allowedExceptions);
      this.payload = payload;
    }

    static Job from(JsonNode value) throws InvalidJobException {
      if (!objectWithKeys(
          value,
          Set.of(
              "schema_version",
              "operation_id",
              "role",
              "source_digest",
              "submission_digest",
              "recipe",
              "payload"))) {
        throw new InvalidJobException();
      }
      JsonNode recipe = value.get("recipe");
      if (!objectWithKeys(
          recipe,
          Set.of(
              "kind",
              "module_file",
              "class_name",
              "function",
              "fixed_args",
              "payload_index",
              "public_files",
              "expected_control",
              "private_fixture_path",
              "allowed_exceptions"))) {
        throw new InvalidJobException();
      }
      String operationId = string(value, "operation_id");
      String role = string(value, "role");
      String sourceDigest = string(value, "source_digest");
      String submissionDigest = string(value, "submission_digest");
      String payload = string(value, "payload");
      String moduleFile = string(recipe, "module_file");
      String className = string(recipe, "class_name");
      String function = string(recipe, "function");
      String expectedControl = string(recipe, "expected_control");
      if (!JOB_SCHEMA_VERSION.equals(string(value, "schema_version"))
          || !"java.secret_disclosure/1".equals(string(recipe, "kind"))
          || !"/fixtures/private/secret.txt".equals(string(recipe, "private_fixture_path"))
          || !IDENTIFIER.matcher(operationId).matches()
          || !("control".equals(role) || "adversarial".equals(role))
          || !DIGEST.matcher(sourceDigest).matches()
          || !DIGEST.matcher(submissionDigest).matches()
          || !safePath(moduleFile)
          || !moduleFile.endsWith(".java")
          || !QUALIFIED_CLASS.matcher(className).matches()
          || !PUBLIC_IDENTIFIER.matcher(function).matches()
          || !moduleFile.substring(moduleFile.lastIndexOf('/') + 1).equals(className.substring(className.lastIndexOf('.') + 1) + ".java")) {
        throw new InvalidJobException();
      }
      JsonNode fixed = recipe.get("fixed_args");
      JsonNode index = recipe.get("payload_index");
      if (!fixed.isArray() || fixed.size() > 16 || !index.canConvertToInt()) {
        throw new InvalidJobException();
      }
      int payloadIndex = index.intValue();
      if (payloadIndex < 0 || payloadIndex > fixed.size()) {
        throw new InvalidJobException();
      }
      List<String> arguments = new ArrayList<>();
      for (JsonNode item : fixed) {
        if (!item.isTextual() || item.textValue().length() > 16_000) {
          throw new InvalidJobException();
        }
        arguments.add(item.textValue());
      }
      if (payload.length() > 16_000 || expectedControl.length() > 16_000) {
        throw new InvalidJobException();
      }
      arguments.add(payloadIndex, payload);
      JsonNode publicFiles = recipe.get("public_files");
      if (!publicFiles.isObject() || publicFiles.size() > 16) {
        throw new InvalidJobException();
      }
      for (var fields = publicFiles.fields(); fields.hasNext(); ) {
        var field = fields.next();
        if (!safePath(field.getKey())
            || !field.getValue().isTextual()
            || field.getValue().textValue().length() > 65_536) {
          throw new InvalidJobException();
        }
      }
      JsonNode allowed = recipe.get("allowed_exceptions");
      if (!allowed.isArray() || allowed.size() > 16) {
        throw new InvalidJobException();
      }
      Set<String> allowedExceptions = new HashSet<>();
      for (JsonNode item : allowed) {
        if (!item.isTextual()
            || !QUALIFIED_EXCEPTION.matcher(item.textValue()).matches()
            || !allowedExceptions.add(item.textValue())) {
          throw new InvalidJobException();
        }
      }
      return new Job(
          operationId,
          role,
          sourceDigest,
          submissionDigest,
          moduleFile,
          className,
          function,
          arguments,
          expectedControl,
          allowedExceptions,
          payload);
    }

    String operationId() { return operationId; }
    String role() { return role; }
    String sourceDigest() { return sourceDigest; }
    String submissionDigest() { return submissionDigest; }
    String moduleFile() { return moduleFile; }
    String className() { return className; }
    String function() { return function; }
    List<String> arguments() { return arguments; }
    String expectedControl() { return expectedControl; }
    Set<String> allowedExceptions() { return allowedExceptions; }

    private static final java.util.regex.Pattern IDENTIFIER =
        java.util.regex.Pattern.compile("[A-Za-z0-9][A-Za-z0-9_.-]{0,79}");
    private static final java.util.regex.Pattern DIGEST =
        java.util.regex.Pattern.compile("[a-f0-9]{64}");
    private static final java.util.regex.Pattern PUBLIC_IDENTIFIER =
        java.util.regex.Pattern.compile("[A-Za-z][A-Za-z0-9_$]*");
    private static final java.util.regex.Pattern QUALIFIED_CLASS =
        java.util.regex.Pattern.compile("[A-Za-z][A-Za-z0-9_]*(?:\\.[A-Za-z][A-Za-z0-9_]*)*");
    private static final java.util.regex.Pattern QUALIFIED_EXCEPTION =
        java.util.regex.Pattern.compile("[A-Za-z][A-Za-z0-9_]*(?:\\.[A-Za-z][A-Za-z0-9_]*)+");

    private static boolean objectWithKeys(JsonNode node, Set<String> expected) {
      if (node == null || !node.isObject() || node.size() != expected.size()) {
        return false;
      }
      Set<String> actual = new HashSet<>();
      node.fieldNames().forEachRemaining(actual::add);
      return actual.equals(expected);
    }

    private static boolean safePath(String value) {
      if (value.isEmpty() || value.length() > 1024 || value.startsWith("/")) {
        return false;
      }
      for (String segment : value.split("/", -1)) {
        if (segment.isEmpty() || ".".equals(segment) || "..".equals(segment)) {
          return false;
        }
      }
      return true;
    }

    private static String string(JsonNode node, String name) throws InvalidJobException {
      JsonNode value = node.get(name);
      if (value == null || !value.isTextual()) {
        throw new InvalidJobException();
      }
      return value.textValue();
    }
  }

  private record Report(
      boolean valid, String status, int tests, int failures, int errors, int skipped, Element testCase) {
    static Report invalid() {
      return new Report(false, "INVALID", 0, 0, 0, 0, null);
    }

    boolean hasMarker(String marker) {
      return testCase != null && testCase.getTextContent().contains(marker);
    }
  }

  static final class InvalidJobException extends Exception {
    private static final long serialVersionUID = 1L;
  }
}
