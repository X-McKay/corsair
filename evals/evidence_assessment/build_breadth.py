"""Generate the `breadth` pre-execution validity cases (Java, JavaScript, Ruby, Perl) from readable source and tests.

Each case is an outcome-blind ``ValidityInput`` as ``composition.evidence.review_items`` lays it out: the typed
``ObservationPlan`` (unit_test mode), the test plan text, the reported condition, the application source of the
baseline revision and the frozen test patch. Digests are computed here, never written by hand:

- item ``sha256``: SHA-256 of the item content (what ``EvidenceItem`` checks);
- ``frozen_patch_sha256``: ``ApprovedPatch.sha256`` over the patch files (path, length, content);
- source identity (``revision_sources`` and each source item's ``source_sha256``): the same path/length/content
  digest over the baseline source files, standing in for the workspace source digest of a captured revision;
- ``test_plan_sha256``: SHA-256 of the test-plan text item (production digests the typed ``ReadyTestPlan``; these
  cases carry the plan as text, as the existing unit set does).

The oracle constrains only the validity flags a case's property decides; case names, families and oracles never
enter an item. Run ``python -m evals.evidence_assessment.build_breadth`` to rewrite ``cases/``, then freeze the set
with ``python -m evals.cases evidence_assessment breadth --freeze``; ``--check`` compares without writing.
"""
import argparse
import json
import sys
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from textwrap import dedent, indent

from corsair.agents.evidence_assessment.contracts import ValidityInput
from corsair.core.disposition import ExpectedFailure, ObservationPlan
from corsair.ports.test_runner import native_test_function

CASES = Path(__file__).with_name("cases")
FLAGS = ("source_linked", "condition_exercised", "assertions_relevant", "dependency_scope_valid")
VALID = dict.fromkeys(FLAGS, True)
SYNTHETIC = {"source": "synthetic", "license": "n/a (synthetic)",
             "notes": "Written for this set; the property under review is in the frozen test patch, not the source."}


def text(value: str) -> str:
    """Dedented block; a literal opening with a blank line keeps one, so concatenated parts stay separated."""
    body = dedent(value).lstrip("\n")
    return "\n" + body if value.startswith("\n\n") else body


def files_digest(files: tuple[tuple[str, str], ...]) -> str:
    """ApprovedPatch.sha256: order-independent over path, byte length and content."""
    digest = sha256()
    for path, content in sorted(files):
        data = content.encode()
        digest.update(path.encode() + b"\0" + str(len(data)).encode() + b"\0" + data)
    return digest.hexdigest()


@dataclass(frozen=True)
class Scenario:
    language: str
    family: str
    sources: tuple[tuple[str, str], ...]
    test_path: str
    control_id: str
    security_id: str
    failure_type: str
    safe_behavior: str
    test_plan: str
    condition: str


@dataclass(frozen=True)
class Spec:
    name: str
    scenario: Scenario
    framework: str
    patch: str
    assert_on: tuple[str, ...]
    oracle: dict
    probes: str
    extra_sources: tuple[tuple[str, str], ...] = ()
    failure_type: str | None = None
    kind: str = field(default="negative")


def item(item_id: str, kind: str, content: str, **extra) -> dict:
    return {"item_id": item_id, "kind": kind, "revision": extra.pop("revision", None), "run": extra.pop("run", None),
            "sha256": sha256(content.encode()).hexdigest(), **extra, "content": content}


def assertion_lines(patch: str, markers: tuple[str, ...]) -> tuple[int, ...]:
    lines = patch.splitlines()
    found = []
    for marker in markers:
        hits = [number for number, line in enumerate(lines, 1) if marker in line]
        if len(hits) != 1:
            raise ValueError(f"assertion marker {marker!r} matches lines {hits}")
        found.append(hits[0])
    return tuple(sorted(found))


def build(spec: Spec) -> dict[str, dict]:
    scenario = spec.scenario
    sources = scenario.sources + spec.extra_sources
    identity = files_digest(sources)
    plan = ObservationPlan(
        control_test_id=scenario.control_id, security_test_id=scenario.security_id,
        expected_failure=ExpectedFailure(exception_type=spec.failure_type or scenario.failure_type,
                                         path=scenario.test_path,
                                         function=native_test_function(scenario.security_id),
                                         assertion_lines=assertion_lines(spec.patch, spec.assert_on)),
        expected_safe_behavior=scenario.safe_behavior,
        frozen_patch_sha256=files_digest(((scenario.test_path, spec.patch),)),
        observation_mode="unit_test", test_plan_sha256=sha256(scenario.test_plan.encode()).hexdigest())
    items = [item("plan", "plan", plan.model_dump_json(indent=2)),
             item("test-plan", "plan", scenario.test_plan),
             item("reported-condition", "plan", scenario.condition)]
    items += [item(f"baseline-source-{index}", "source", content, revision="baseline", run=0, path=path,
                   source_sha256=identity) for index, (path, content) in enumerate(sources)]
    items.append(item("patch-0", "patch", spec.patch, path=scenario.test_path))
    inputs = {"scope": "component", "plan": json.loads(plan.model_dump_json()),
              "revision_sources": {"baseline": identity}, "items": items}
    ValidityInput.model_validate_json(json.dumps(inputs))
    if set(spec.oracle) - set(FLAGS) or (spec.kind == "positive") != (spec.oracle == VALID):
        raise ValueError(f"{spec.name}: oracle does not match its kind")
    case = {"language": scenario.language, "framework": spec.framework, "family": scenario.family,
            "kind": spec.kind, "probes": spec.probes, "provenance": SYNTHETIC}
    return {"input": inputs, "oracle": spec.oracle, "case": case}


# ----------------------------------------------------------------------------------------------- Java (JUnit, Maven)

JAVA_DOCS = Scenario(
    "java", "path-traversal",
    (("src/main/java/com/example/files/DocumentStore.java", text("""
        package com.example.files;

        import java.io.IOException;
        import java.nio.charset.StandardCharsets;
        import java.nio.file.Files;
        import java.nio.file.Path;

        public final class DocumentStore {
            private final Path root;

            public DocumentStore(Path root) {
                this.root = root.toAbsolutePath().normalize();
            }

            public String read(String name) throws IOException {
                Path target = root.resolve(name).normalize();
                if (!target.startsWith(root)) {
                    throw new IllegalArgumentException("outside root");
                }
                return new String(Files.readAllBytes(target), StandardCharsets.UTF_8);
            }
        }
        """)),),
    "src/test/java/com/example/files/DocumentStoreTest.java",
    "com.example.files.DocumentStoreTest#controlReadsDocumentInsideRoot",
    "com.example.files.DocumentStoreTest#exploitRejectsParentTraversal",
    "org.opentest4j.AssertionFailedError", "java.lang.IllegalArgumentException",
    "Exactly two JUnit probes in DocumentStoreTest. Control: write note.txt under a temporary docs root and assert "
    "new DocumentStore(root).read(\"note.txt\") returns hello. Exploit: place secret.txt beside the root, call "
    "read(\"../secret.txt\") and assert IllegalArgumentException with message outside root. DocumentStore.read in "
    "src/main/java/com/example/files/DocumentStore.java owns the containment check. The filesystem is a temporary "
    "directory; DocumentStore itself is never replaced.",
    "Document names from the download endpoint reach DocumentStore.read unchanged. A name such as ../secret.txt may "
    "resolve outside the configured document root and return another file's contents.")

JAVA_DOCS_HEAD = text("""
    package com.example.files;

    import static org.junit.jupiter.api.Assertions.assertEquals;
    import static org.junit.jupiter.api.Assertions.assertThrows;

    import java.nio.charset.StandardCharsets;
    import java.nio.file.Files;
    import java.nio.file.Path;
    import org.junit.jupiter.api.Test;
    import org.junit.jupiter.api.io.TempDir;
    """)

JAVA_DOCS_CONTROL = """
    @Test
    void controlReadsDocumentInsideRoot() throws Exception {
        Path root = Files.createDirectory(tmp.resolve("docs"));
        Files.write(root.resolve("note.txt"), "hello".getBytes(StandardCharsets.UTF_8));
        assertEquals("hello", new DocumentStore(root).read("note.txt"));
    }
"""

JAVA_USERS = Scenario(
    "java", "sql-injection",
    (("src/main/java/com/example/users/QueryExecutor.java", text("""
        package com.example.users;

        import java.util.List;

        public interface QueryExecutor {
            List<Long> queryIds(String sql, List<Object> parameters);
        }
        """)),
     ("src/main/java/com/example/users/UserLookup.java", text("""
        package com.example.users;

        import java.util.Collections;
        import java.util.List;
        import java.util.Optional;

        public final class UserLookup {
            static final String BY_NAME = "SELECT id FROM users WHERE name = ?";
            private final QueryExecutor executor;

            public UserLookup(QueryExecutor executor) {
                this.executor = executor;
            }

            public Optional<Long> findIdByName(String name) {
                List<Long> ids = executor.queryIds(BY_NAME, Collections.singletonList(name));
                return ids.isEmpty() ? Optional.empty() : Optional.of(ids.get(0));
            }
        }
        """))),
    "src/test/java/com/example/users/UserLookupTest.java",
    "com.example.users.UserLookupTest#controlFindsUserByName",
    "com.example.users.UserLookupTest#exploitKeepsQuoteInBoundParameter",
    "org.opentest4j.AssertionFailedError", "bound_parameter",
    "Exactly two JUnit 5 probes in UserLookupTest. Control: look up alice through a recording QueryExecutor that "
    "returns id 7 and assert Optional.of(7L). Exploit: look up alice' OR '1'='1 and assert the executor received the "
    "constant statement SELECT id FROM users WHERE name = ? with the whole input as its single bound parameter. "
    "UserLookup.findIdByName owns query construction. Only the QueryExecutor database dependency may be doubled; the "
    "double records calls and does not decide safety. Database engine behavior is out of scope.",
    "User names from the search form reach UserLookup.findIdByName. A value such as alice' OR '1'='1 could change "
    "the SQL statement if it were concatenated into the query text.")

JAVA_USERS_HEAD = text("""
    package com.example.users;

    import static org.junit.jupiter.api.Assertions.assertEquals;
    import static org.junit.jupiter.api.Assertions.assertThrows;

    import java.util.ArrayList;
    import java.util.Collections;
    import java.util.List;
    import java.util.Optional;
    import org.junit.jupiter.api.Test;

    class UserLookupTest {
        static final class RecordingExecutor implements QueryExecutor {
            final List<String> statements = new ArrayList<>();
            final List<List<Object>> parameters = new ArrayList<>();

            @Override
            public List<Long> queryIds(String sql, List<Object> params) {
                statements.add(sql);
                parameters.add(params);
                return Collections.singletonList(7L);
            }
        }

        @Test
        void controlFindsUserByName() {
            RecordingExecutor executor = new RecordingExecutor();
            assertEquals(Optional.of(7L), new UserLookup(executor).findIdByName("alice"));
            assertEquals(Collections.singletonList("alice"), executor.parameters.get(0));
        }
    """)

JAVA_XML = Scenario(
    "java", "xxe",
    (("src/main/java/com/example/xml/ConfigParser.java", text("""
        package com.example.xml;

        import java.io.ByteArrayInputStream;
        import java.nio.charset.StandardCharsets;
        import javax.xml.parsers.DocumentBuilder;
        import javax.xml.parsers.DocumentBuilderFactory;
        import org.w3c.dom.Document;

        public final class ConfigParser {
            public String serviceName(String xml) throws Exception {
                DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
                factory.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
                factory.setExpandEntityReferences(false);
                DocumentBuilder builder = factory.newDocumentBuilder();
                Document document = builder.parse(new ByteArrayInputStream(xml.getBytes(StandardCharsets.UTF_8)));
                return document.getDocumentElement().getElementsByTagName("name").item(0).getTextContent();
            }
        }
        """)),),
    "src/test/java/com/example/xml/ConfigParserTest.java",
    "com.example.xml.ConfigParserTest#controlParsesServiceName",
    "com.example.xml.ConfigParserTest#exploitRejectsExternalEntity",
    "org.opentest4j.AssertionFailedError", "org.xml.sax.SAXParseException",
    "Exactly two JUnit 5 probes in ConfigParserTest. Control: parse <config><name>billing</name></config> and assert "
    "serviceName returns billing. Exploit: parse a document whose DOCTYPE declares an external entity for "
    "file:///etc/hostname referenced inside <name>, and assert org.xml.sax.SAXParseException from "
    "ConfigParser.serviceName. ConfigParser.serviceName owns parser hardening; the JDK parser is used as is.",
    "Uploaded service configuration XML is parsed by ConfigParser.serviceName. A DOCTYPE with an external entity may "
    "make the parser read local files into the service name.")

JAVA_XML_HEAD = text("""
    package com.example.xml;

    import static org.junit.jupiter.api.Assertions.assertEquals;
    import static org.junit.jupiter.api.Assertions.assertNotNull;
    import static org.junit.jupiter.api.Assertions.assertThrows;
    import static org.junit.jupiter.api.Assertions.assertTrue;

    import org.junit.jupiter.api.Test;
    import org.xml.sax.SAXParseException;

    class ConfigParserTest {
        static final String PAYLOAD = "<?xml version=\\"1.0\\"?>"
                + "<!DOCTYPE config [<!ENTITY host SYSTEM \\"file:///etc/hostname\\">]>"
                + "<config><name>&host;</name></config>";
    """)

JAVA_GREETING = Scenario(
    "java", "xss",
    (("src/main/java/com/example/web/Greeting.java", text("""
        package com.example.web;

        public final class Greeting {
            public String render(String name) {
                StringBuilder out = new StringBuilder("<p>Hello, ");
                for (char c : name.toCharArray()) {
                    switch (c) {
                        case '<': out.append("&lt;"); break;
                        case '>': out.append("&gt;"); break;
                        case '&': out.append("&amp;"); break;
                        case '"': out.append("&quot;"); break;
                        case '\\'': out.append("&#39;"); break;
                        default: out.append(c);
                    }
                }
                return out.append("</p>").toString();
            }
        }
        """)),),
    "src/test/java/com/example/web/GreetingTest.java",
    "com.example.web.GreetingTest#controlRendersPlainName",
    "com.example.web.GreetingTest#exploitEscapesScriptTag",
    "org.opentest4j.AssertionFailedError", "html_escaped",
    "Exactly two JUnit 5 probes in GreetingTest. Control: render Ada and assert <p>Hello, Ada</p>. Exploit: render "
    "<script>alert(1)</script> and assert the exact output <p>Hello, &lt;script&gt;alert(1)&lt;/script&gt;</p>, so "
    "no raw script tag reaches the page. Greeting.render owns escaping.",
    "Display names are rendered into the dashboard header by Greeting.render. A name such as "
    "<script>alert(1)</script> may execute in other users' browsers.")

JAVA = [
    Spec("java-valid-traversal-return-and-exception", JAVA_DOCS, "junit5", JAVA_DOCS_HEAD + text("""

        class DocumentStoreTest {
            @TempDir
            Path tmp;
        """) + JAVA_DOCS_CONTROL + text("""

            @Test
            void exploitRejectsParentTraversal() throws Exception {
                Path root = Files.createDirectory(tmp.resolve("docs"));
                Files.write(tmp.resolve("secret.txt"), "token".getBytes(StandardCharsets.UTF_8));
                DocumentStore store = new DocumentStore(root);
                IllegalArgumentException error = assertThrows(IllegalArgumentException.class,
                        () -> store.read("../secret.txt"));
                assertEquals("outside root", error.getMessage());
            }
        }
        """),
         ("assertThrows(IllegalArgumentException.class,",), VALID,
         "Real DocumentStore seam: the control returns file content and the exploit asserts the specific rejection "
         "exception raised by production containment.", kind="positive"),
    Spec("java-valid-recording-query-executor", JAVA_USERS, "junit5", JAVA_USERS_HEAD + text("""

            @Test
            void exploitKeepsQuoteInBoundParameter() {
                RecordingExecutor executor = new RecordingExecutor();
                String payload = "alice' OR '1'='1";
                new UserLookup(executor).findIdByName(payload);
                assertEquals("SELECT id FROM users WHERE name = ?", executor.statements.get(0));
                assertEquals(Collections.singletonList(payload), executor.parameters.get(0));
            }
        }
        """),
         ('assertEquals("SELECT id FROM users', "assertEquals(Collections.singletonList(payload)"), VALID,
         "A recording double replaces only the database executor; production UserLookup still builds the statement "
         "and binds the payload, which both assertions check.", kind="positive"),
    Spec("java-copied-traversal-guard", JAVA_DOCS, "junit5", JAVA_DOCS_HEAD.replace("import java.nio.charset", "import java.io.IOException;\nimport java.nio.charset")
         + text("""

        class DocumentStoreTest {
            @TempDir
            Path tmp;

            private static String read(Path root, String name) throws IOException {
                Path base = root.toAbsolutePath().normalize();
                Path target = base.resolve(name).normalize();
                if (!target.startsWith(base)) {
                    throw new IllegalArgumentException("outside root");
                }
                return new String(Files.readAllBytes(target), StandardCharsets.UTF_8);
            }

            @Test
            void controlReadsDocumentInsideRoot() throws Exception {
                Path root = Files.createDirectory(tmp.resolve("docs"));
                Files.write(root.resolve("note.txt"), "hello".getBytes(StandardCharsets.UTF_8));
                assertEquals("hello", read(root, "note.txt"));
            }

            @Test
            void exploitRejectsParentTraversal() throws Exception {
                Path root = Files.createDirectory(tmp.resolve("docs"));
                Files.write(tmp.resolve("secret.txt"), "token".getBytes(StandardCharsets.UTF_8));
                IllegalArgumentException error = assertThrows(IllegalArgumentException.class,
                        () -> read(root, "../secret.txt"));
                assertEquals("outside root", error.getMessage());
            }
        }
        """), ("assertThrows(IllegalArgumentException.class,",), {"source_linked": False},
         "Both probes call a private copy of the containment logic declared in the test class instead of "
         "DocumentStore.read."),
    Spec("java-mockito-spy-entry-point", JAVA_DOCS, "junit5", JAVA_DOCS_HEAD.replace(
        "import static org.junit.jupiter.api.Assertions.assertThrows;\n",
        "import static org.junit.jupiter.api.Assertions.assertThrows;\nimport static org.mockito.Mockito.doThrow;\n"
        "import static org.mockito.Mockito.spy;\n") + text("""

        class DocumentStoreTest {
            @TempDir
            Path tmp;
        """) + JAVA_DOCS_CONTROL + text("""

            @Test
            void exploitRejectsParentTraversal() throws Exception {
                Path root = Files.createDirectory(tmp.resolve("docs"));
                Files.write(tmp.resolve("secret.txt"), "token".getBytes(StandardCharsets.UTF_8));
                DocumentStore store = spy(new DocumentStore(root));
                doThrow(new IllegalArgumentException("outside root")).when(store).read("../secret.txt");
                IllegalArgumentException error = assertThrows(IllegalArgumentException.class,
                        () -> store.read("../secret.txt"));
                assertEquals("outside root", error.getMessage());
            }
        }
        """),
         ("assertThrows(IllegalArgumentException.class,",), {"source_linked": False},
         "The control uses the real store, but the exploit stubs DocumentStore.read itself with a Mockito spy, so "
         "the asserted rejection comes from the stub."),
    Spec("java-vacuous-xxe-assertions", JAVA_XML, "junit5", JAVA_XML_HEAD + text("""

            @Test
            void controlParsesServiceName() throws Exception {
                String name = new ConfigParser().serviceName("<config><name>billing</name></config>");
                assertNotNull(name);
            }

            @Test
            void exploitRejectsExternalEntity() {
                ConfigParser parser = new ConfigParser();
                try {
                    parser.serviceName(PAYLOAD);
                } catch (Exception ignored) {
                    // parser stopped
                }
                assertTrue(true);
            }
        }
        """),
         ("assertTrue(true);",), {"assertions_relevant": False},
         "Both XXE probes call the real parser with the right inputs, but the exploit swallows any exception and "
         "asserts a constant."),
    Spec("java-double-owns-quote-rejection", JAVA_USERS, "junit5", text("""
        package com.example.users;

        import static org.junit.jupiter.api.Assertions.assertEquals;
        import static org.junit.jupiter.api.Assertions.assertThrows;

        import java.util.Collections;
        import java.util.List;
        import java.util.Optional;
        import org.junit.jupiter.api.Test;

        class UserLookupTest {
            static final class QuoteRejectingExecutor implements QueryExecutor {
                @Override
                public List<Long> queryIds(String sql, List<Object> params) {
                    for (Object value : params) {
                        if (String.valueOf(value).contains("'")) {
                            throw new IllegalArgumentException("unsafe query parameter");
                        }
                    }
                    return Collections.singletonList(7L);
                }
            }

            @Test
            void controlFindsUserByName() {
                assertEquals(Optional.of(7L), new UserLookup(new QuoteRejectingExecutor()).findIdByName("alice"));
            }

            @Test
            void exploitKeepsQuoteInBoundParameter() {
                UserLookup lookup = new UserLookup(new QuoteRejectingExecutor());
                assertThrows(IllegalArgumentException.class, () -> lookup.findIdByName("alice' OR '1'='1"));
            }
        }
        """), ("assertThrows(IllegalArgumentException.class",), {"dependency_scope_valid": False},
         "The executor double rejects quoted values itself, so the asserted safety is decided by the double rather "
         "than by UserLookup's statement construction."),
    Spec("java-junit4-legacy-reader-class", JAVA_DOCS, "junit4", text("""
        package com.example.files;

        import static org.junit.Assert.assertEquals;
        import static org.junit.Assert.assertThrows;

        import java.io.File;
        import java.nio.charset.StandardCharsets;
        import java.nio.file.Files;
        import java.nio.file.Path;
        import org.junit.Rule;
        import org.junit.Test;
        import org.junit.rules.TemporaryFolder;

        public class DocumentStoreTest {
            @Rule
            public TemporaryFolder tmp = new TemporaryFolder();

            @Test
            public void controlReadsDocumentInsideRoot() throws Exception {
                Path root = tmp.newFolder("docs").toPath();
                Files.write(root.resolve("note.txt"), "hello".getBytes(StandardCharsets.UTF_8));
                assertEquals("hello", LegacyDocumentReader.read(root, "note.txt"));
            }

            @Test
            public void exploitRejectsParentTraversal() throws Exception {
                Path root = tmp.newFolder("docs").toPath();
                File secret = tmp.newFile("secret.txt");
                Files.write(secret.toPath(), "token".getBytes(StandardCharsets.UTF_8));
                IllegalArgumentException error = assertThrows(IllegalArgumentException.class,
                        () -> LegacyDocumentReader.read(root, "../secret.txt"));
                assertEquals("outside root", error.getMessage());
            }
        }
        """), ("assertThrows(IllegalArgumentException.class,",), {"source_linked": False},
         "A JUnit 4 pair that exercises the reported input against LegacyDocumentReader, a different class with its "
         "own check, instead of DocumentStore.read named by the plan.",
         extra_sources=(("src/main/java/com/example/files/LegacyDocumentReader.java", text("""
            package com.example.files;

            import java.io.IOException;
            import java.nio.charset.StandardCharsets;
            import java.nio.file.Files;
            import java.nio.file.Path;

            public final class LegacyDocumentReader {
                private LegacyDocumentReader() {
                }

                public static String read(Path root, String name) throws IOException {
                    if (name.contains("..")) {
                        throw new IllegalArgumentException("outside root");
                    }
                    return new String(Files.readAllBytes(root.resolve(name)), StandardCharsets.UTF_8);
                }
            }
            """)),), failure_type="java.lang.AssertionError"),
    Spec("java-benign-document-for-xxe-exploit", JAVA_XML, "junit5", JAVA_XML_HEAD + text("""

            @Test
            void controlParsesServiceName() throws Exception {
                assertEquals("billing", new ConfigParser().serviceName("<config><name>billing</name></config>"));
            }

            @Test
            void exploitRejectsExternalEntity() {
                ConfigParser parser = new ConfigParser();
                assertThrows(SAXParseException.class,
                        () -> parser.serviceName("<config><name>reports</name></config>"));
            }
        }
        """),
         ("assertThrows(SAXParseException.class,",), {"condition_exercised": False},
         "The exploit expects the parser's rejection but feeds a plain document without a DOCTYPE or entity, so the "
         "reported input is never exercised."),
    Spec("java-unrelated-call-count-assertion", JAVA_USERS, "junit5", JAVA_USERS_HEAD + text("""

            @Test
            void exploitKeepsQuoteInBoundParameter() {
                RecordingExecutor executor = new RecordingExecutor();
                new UserLookup(executor).findIdByName("alice' OR '1'='1");
                assertEquals(1, executor.statements.size());
            }
        }
        """),
         ("assertEquals(1, executor.statements.size());",), {"assertions_relevant": False},
         "The exploit sends the injection payload through the real lookup but asserts only that one statement ran, "
         "which holds whether or not the payload was concatenated."),
    Spec("java-exploit-asserts-only-no-exception", JAVA_GREETING, "junit5", text("""
        package com.example.web;

        import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
        import static org.junit.jupiter.api.Assertions.assertEquals;

        import org.junit.jupiter.api.Test;

        class GreetingTest {
            @Test
            void controlRendersPlainName() {
                assertEquals("<p>Hello, Ada</p>", new Greeting().render("Ada"));
            }

            @Test
            void exploitEscapesScriptTag() {
                assertDoesNotThrow(() -> new Greeting().render("<script>alert(1)</script>"));
            }
        }
        """), ("assertDoesNotThrow(",), {"assertions_relevant": False},
         "The XSS exploit renders the script payload through the real Greeting but asserts only that no exception "
         "was thrown, not that the output is escaped."),
    Spec("java-early-return-before-traversal", JAVA_DOCS, "junit5", JAVA_DOCS_HEAD + text("""

        class DocumentStoreTest {
            @TempDir
            Path tmp;
        """) + JAVA_DOCS_CONTROL + text("""

            @Test
            void exploitRejectsParentTraversal() throws Exception {
                Path root = Files.createDirectory(tmp.resolve("docs"));
                Path secret = tmp.resolve("secret.txt");
                if (!Files.exists(secret)) {
                    return;
                }
                DocumentStore store = new DocumentStore(root);
                IllegalArgumentException error = assertThrows(IllegalArgumentException.class,
                        () -> store.read("../secret.txt"));
                assertEquals("outside root", error.getMessage());
            }
        }
        """),
         ("assertThrows(IllegalArgumentException.class,",), {"condition_exercised": False},
         "The exploit returns early because the secret fixture it checks for is never created, so the traversal "
         "call is never reached."),
]

# ----------------------------------------------------------------------------------------------- JavaScript (Jest 24)

JS_SETVALUE = Scenario(
    "javascript", "prototype-pollution",
    (("lib/set-value.js", text("""
        'use strict';

        const BLOCKED = ['__proto__', 'constructor', 'prototype'];

        function setValue(target, path, value) {
          const keys = path.split('.');
          let node = target;
          keys.forEach((key, index) => {
            if (BLOCKED.indexOf(key) !== -1) {
              throw new Error('unsafe key: ' + key);
            }
            if (index === keys.length - 1) {
              node[key] = value;
              return;
            }
            if (typeof node[key] !== 'object' || node[key] === null) {
              node[key] = {};
            }
            node = node[key];
          });
          return target;
        }

        module.exports = { setValue };
        """)),),
    "test/set-value.test.js", "test/set-value.test.js::control_sets_nested_value",
    "test/set-value.test.js::exploit_rejects_proto_path", "Error", "Error",
    "Exactly two Jest probes in test/set-value.test.js. Control: setValue({}, 'theme.color', 'dark') returns "
    "{theme: {color: 'dark'}}. Exploit: setValue({}, '__proto__.polluted', 'yes') throws an Error matching unsafe key, "
    "and a fresh object has no polluted property afterwards. setValue in lib/set-value.js owns key filtering; it is "
    "required directly and never mocked.",
    "Settings paths from the preferences API are passed to setValue. A path starting with __proto__ may write onto "
    "Object.prototype and change every object in the process.")

JS_ASSETS = Scenario(
    "javascript", "path-traversal",
    (("lib/assets.js", text("""
        'use strict';

        const path = require('path');

        function readAsset(root, name, fs) {
          const files = fs || require('fs');
          const base = files.realpathSync(root);
          const full = files.realpathSync(path.resolve(base, name));
          if (full !== base && full.indexOf(base + path.sep) !== 0) {
            throw new Error('outside root');
          }
          return files.readFileSync(full, 'utf8');
        }

        module.exports = { readAsset };
        """)),),
    "test/assets.test.js", "test/assets.test.js::control_reads_asset",
    "test/assets.test.js::exploit_rejects_parent_path", "Error", "Error",
    "Exactly two Jest probes in test/assets.test.js. Control: read logo.svg from /srv/assets and assert its content. "
    "Exploit: request ../config/secrets.json, assert Error outside root and assert no file was read. readAsset in "
    "lib/assets.js owns the containment check. The fs dependency may be an in-memory double that resolves paths and "
    "returns contents without judging them; readAsset itself is never replaced.",
    "Asset names from /static/:name are passed to readAsset. A name such as ../config/secrets.json may resolve "
    "outside the asset root and be returned to the client.")

JS_MEMORY_FS = text("""
    function memoryFs(files) {
      const reads = [];
      return {
        reads,
        realpathSync: (p) => path.resolve(p),
        readFileSync: (p) => {
          reads.push(p);
          return files[p];
        },
      };
    }

    const FILES = { '/srv/assets/logo.svg': '<svg/>', '/srv/config/secrets.json': '{"token":"t"}' };
    """)

JS_ARCHIVE = Scenario(
    "javascript", "command-injection",
    (("lib/archive.js", text("""
        'use strict';

        const { execFileSync } = require('child_process');

        const NAME = /^[A-Za-z0-9._-]+$/;

        function archiveReport(name, run) {
          const exec = run || execFileSync;
          if (!NAME.test(name)) {
            throw new Error('invalid archive name');
          }
          return exec('tar', ['-czf', name + '.tgz', 'reports']);
        }

        module.exports = { archiveReport };
        """)),),
    "test/archive.test.js", "test/archive.test.js::control_archives_report",
    "test/archive.test.js::exploit_rejects_shell_name", "Error", "Error",
    "Exactly two Jest probes in test/archive.test.js. Control: archive weekly with a jest.fn runner and assert it "
    "received tar with ['-czf', 'weekly.tgz', 'reports']. Exploit: archive 'weekly; touch /tmp/pwned', assert Error "
    "invalid archive name and assert the runner was never called. archiveReport in lib/archive.js owns name "
    "validation; only the process runner may be replaced by a recorder.",
    "Report names from the export form are used to build an archive command. A name containing ; touch /tmp/pwned "
    "may run an extra command on the server.")

JS_ARCHIVE_CONTROL = text("""
    'use strict';

    const { archiveReport } = require('../lib/archive');

    test('control_archives_report', () => {
      const runner = jest.fn();
      archiveReport('weekly', runner);
      expect(runner).toHaveBeenCalledWith('tar', ['-czf', 'weekly.tgz', 'reports']);
    });
    """)

JS_RENDER = Scenario(
    "javascript", "xss",
    (("lib/render.js", text("""
        'use strict';

        const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

        function renderComment(text) {
          return '<p class="comment">' + String(text).replace(/[&<>"']/g, (c) => ESCAPES[c]) + '</p>';
        }

        module.exports = { renderComment };
        """)),),
    "test/render.test.js", "test/render.test.js::control_renders_plain_comment",
    "test/render.test.js::exploit_escapes_markup", "Error", "html_escaped",
    "Exactly two Jest probes in test/render.test.js. Control: renderComment('hello') returns "
    "<p class=\"comment\">hello</p>. Exploit: renderComment('<img src=x onerror=alert(1)>') returns the exact escaped "
    "markup <p class=\"comment\">&lt;img src=x onerror=alert(1)&gt;</p> with no raw img tag. renderComment in "
    "lib/render.js owns escaping.",
    "Comment bodies are rendered with renderComment. A body such as <img src=x onerror=alert(1)> may run script in "
    "other readers' browsers.")

JAVASCRIPT = [
    Spec("javascript-valid-proto-path-throws", JS_SETVALUE, "jest24", text("""
        'use strict';

        const { setValue } = require('../lib/set-value');

        test('control_sets_nested_value', () => {
          expect(setValue({}, 'theme.color', 'dark')).toEqual({ theme: { color: 'dark' } });
        });

        test('exploit_rejects_proto_path', () => {
          expect(() => setValue({}, '__proto__.polluted', 'yes')).toThrow(/unsafe key/);
          expect({}.polluted).toBeUndefined();
        });
        """), ("toThrow(/unsafe key/)", "expect({}.polluted)"), VALID,
         "Real setValue seam: the control returns the updated object and the exploit asserts the specific rejection "
         "plus the absence of prototype pollution.", kind="positive"),
    Spec("javascript-valid-in-memory-fs-double", JS_ASSETS, "jest24", text("""
        'use strict';

        const path = require('path');
        const { readAsset } = require('../lib/assets');

        """) + JS_MEMORY_FS + text("""

        test('control_reads_asset', () => {
          expect(readAsset('/srv/assets', 'logo.svg', memoryFs(FILES))).toBe('<svg/>');
        });

        test('exploit_rejects_parent_path', () => {
          const fs = memoryFs(FILES);
          expect(() => readAsset('/srv/assets', '../config/secrets.json', fs)).toThrow('outside root');
          expect(fs.reads).toEqual([]);
        });
        """), ("toThrow('outside root')", "expect(fs.reads)"), VALID,
         "An in-memory fs double only resolves and returns files; production readAsset still performs the "
         "containment check the exploit asserts.", kind="positive"),
    Spec("javascript-copied-asset-guard", JS_ASSETS, "jest24", text("""
        'use strict';

        const path = require('path');

        function readAsset(root, name, files) {
          const base = files.realpathSync(root);
          const full = files.realpathSync(path.resolve(base, name));
          if (full !== base && full.indexOf(base + path.sep) !== 0) {
            throw new Error('outside root');
          }
          return files.readFileSync(full, 'utf8');
        }

        """) + JS_MEMORY_FS + text("""

        test('control_reads_asset', () => {
          expect(readAsset('/srv/assets', 'logo.svg', memoryFs(FILES))).toBe('<svg/>');
        });

        test('exploit_rejects_parent_path', () => {
          const fs = memoryFs(FILES);
          expect(() => readAsset('/srv/assets', '../config/secrets.json', fs)).toThrow('outside root');
          expect(fs.reads).toEqual([]);
        });
        """), ("toThrow('outside root')", "expect(fs.reads)"), {"source_linked": False},
         "The test file declares its own readAsset with the same containment logic and never requires "
         "lib/assets.js."),
    Spec("javascript-jest-mock-module-under-test", JS_SETVALUE, "jest24", text("""
        'use strict';

        jest.mock('../lib/set-value', () => ({
          setValue: jest.fn((target, path, value) => {
            if (path.indexOf('__proto__') === 0) {
              throw new Error('unsafe key: __proto__');
            }
            const [head, tail] = path.split('.');
            target[head] = { [tail]: value };
            return target;
          }),
        }));

        const { setValue } = require('../lib/set-value');

        test('control_sets_nested_value', () => {
          expect(setValue({}, 'theme.color', 'dark')).toEqual({ theme: { color: 'dark' } });
        });

        test('exploit_rejects_proto_path', () => {
          expect(() => setValue({}, '__proto__.polluted', 'yes')).toThrow(/unsafe key/);
          expect({}.polluted).toBeUndefined();
        });
        """), ("toThrow(/unsafe key/)", "expect({}.polluted)"), {"source_linked": False},
         "jest.mock replaces the module under test with a factory, so both probes exercise the mock's own key check "
         "instead of lib/set-value.js."),
    Spec("javascript-vacuous-archive-assertions", JS_ARCHIVE, "jest24", text("""
        'use strict';

        const { archiveReport } = require('../lib/archive');

        test('control_archives_report', () => {
          const runner = jest.fn();
          archiveReport('weekly', runner);
          expect(runner).toBeDefined();
        });

        test('exploit_rejects_shell_name', () => {
          const runner = jest.fn();
          let outcome = 'done';
          try {
            archiveReport('weekly; touch /tmp/pwned', runner);
          } catch (error) {
            outcome = 'done';
          }
          expect(outcome).toBe('done');
        });
        """), ("expect(outcome).toBe('done');",), {"assertions_relevant": False},
         "Both probes call the real archiveReport with the right inputs, but every assertion holds whatever the "
         "function does."),
    Spec("javascript-fs-double-owns-containment", JS_ASSETS, "jest24", text("""
        'use strict';

        const path = require('path');
        const { readAsset } = require('../lib/assets');

        function guardedFs(files) {
          return {
            realpathSync: (p) => {
              const resolved = path.resolve(p);
              if (resolved !== '/srv/assets' && resolved.indexOf('/srv/assets/') !== 0) {
                throw new Error('outside root');
              }
              return resolved;
            },
            readFileSync: (p) => files[p],
          };
        }

        const FILES = { '/srv/assets/logo.svg': '<svg/>', '/srv/config/secrets.json': '{"token":"t"}' };

        test('control_reads_asset', () => {
          expect(readAsset('/srv/assets', 'logo.svg', guardedFs(FILES))).toBe('<svg/>');
        });

        test('exploit_rejects_parent_path', () => {
          expect(() => readAsset('/srv/assets', '../config/secrets.json', guardedFs(FILES))).toThrow('outside root');
        });
        """), ("toThrow('outside root')",), {"dependency_scope_valid": False},
         "The fs double's realpathSync throws for paths outside /srv/assets, so the asserted rejection is raised by "
         "the double before readAsset's own check runs."),
    Spec("javascript-legacy-module-required", JS_ASSETS, "jest24", text("""
        'use strict';

        const fs = require('fs');
        const os = require('os');
        const path = require('path');
        const { loadAsset } = require('../lib/legacy-assets');

        const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'assets-'));
        const root = path.join(dir, 'assets');
        fs.mkdirSync(root);
        fs.writeFileSync(path.join(root, 'logo.svg'), '<svg/>');
        fs.mkdirSync(path.join(dir, 'config'));
        fs.writeFileSync(path.join(dir, 'config', 'secrets.json'), '{"token":"t"}');

        test('control_reads_asset', () => {
          expect(loadAsset(root, 'logo.svg')).toBe('<svg/>');
        });

        test('exploit_rejects_parent_path', () => {
          expect(() => loadAsset(root, '../config/secrets.json')).toThrow('outside root');
        });
        """), ("toThrow('outside root')",), {"source_linked": False},
         "The probes require lib/legacy-assets.js, a different module with its own check, instead of readAsset in "
         "lib/assets.js named by the plan.",
         extra_sources=(("lib/legacy-assets.js", text("""
            'use strict';

            const fs = require('fs');
            const path = require('path');

            function loadAsset(root, name) {
              if (name.indexOf('..') !== -1) {
                throw new Error('outside root');
              }
              return fs.readFileSync(path.join(root, name), 'utf8');
            }

            module.exports = { loadAsset };
            """)),)),
    Spec("javascript-benign-path-for-proto-exploit", JS_SETVALUE, "jest24", text("""
        'use strict';

        const { setValue } = require('../lib/set-value');

        test('control_sets_nested_value', () => {
          expect(setValue({}, 'theme.color', 'dark')).toEqual({ theme: { color: 'dark' } });
        });

        test('exploit_rejects_proto_path', () => {
          expect(() => setValue({}, 'theme.polluted', 'yes')).toThrow(/unsafe key/);
          expect({}.polluted).toBeUndefined();
        });
        """), ("toThrow(/unsafe key/)", "expect({}.polluted)"), {"condition_exercised": False},
         "The exploit asserts the unsafe-key rejection but passes an ordinary nested path, never a __proto__ "
         "segment."),
    Spec("javascript-unrelated-own-keys-assertion", JS_SETVALUE, "jest24", text("""
        'use strict';

        const { setValue } = require('../lib/set-value');

        test('control_sets_nested_value', () => {
          expect(setValue({}, 'theme.color', 'dark')).toEqual({ theme: { color: 'dark' } });
        });

        test('exploit_rejects_proto_path', () => {
          const target = {};
          try {
            setValue(target, '__proto__.polluted', 'yes');
          } catch (error) {
            // rejected
          }
          expect(Object.keys(target)).toEqual([]);
        });
        """), ("expect(Object.keys(target))",), {"assertions_relevant": False},
         "The exploit sends the __proto__ path to the real setValue but asserts only the target's own keys, which "
         "stay empty whether or not Object.prototype was polluted."),
    Spec("javascript-exploit-asserts-only-not-throw", JS_RENDER, "jest24", text("""
        'use strict';

        const { renderComment } = require('../lib/render');

        test('control_renders_plain_comment', () => {
          expect(renderComment('hello')).toBe('<p class="comment">hello</p>');
        });

        test('exploit_escapes_markup', () => {
          expect(() => renderComment('<img src=x onerror=alert(1)>')).not.toThrow();
        });
        """), (".not.toThrow()",), {"assertions_relevant": False},
         "The XSS exploit renders the payload through the real renderComment but asserts only that it does not "
         "throw, not that the markup is escaped."),
    Spec("javascript-env-guard-skips-exploit", JS_ARCHIVE, "jest24", JS_ARCHIVE_CONTROL + text("""

        test('exploit_rejects_shell_name', () => {
          if (!process.env.RUN_SHELL_TESTS) {
            return;
          }
          const runner = jest.fn();
          expect(() => archiveReport('weekly; touch /tmp/pwned', runner)).toThrow('invalid archive name');
          expect(runner).not.toHaveBeenCalled();
        });
        """), ("toThrow('invalid archive name')", "expect(runner).not"), {"condition_exercised": False},
         "The exploit returns before calling archiveReport unless an environment variable the plan never sets is "
         "present, so the shell payload is not exercised."),
]

# ----------------------------------------------------------------------------------------------- Ruby (Minitest)

RUBY_ATTACH = Scenario(
    "ruby", "path-traversal",
    (("lib/attachment_store.rb", text("""
        # frozen_string_literal: true

        class AttachmentStore
          def initialize(root)
            @root = File.realpath(root)
          end

          def read(name)
            path = File.expand_path(name, @root)
            raise ArgumentError, "outside root" unless path.start_with?(@root + File::SEPARATOR)

            File.read(path)
          end
        end
        """)),),
    "test/attachment_store_test.rb", "test/attachment_store_test.rb::AttachmentStoreTest#test_control_reads_attachment",
    "test/attachment_store_test.rb::AttachmentStoreTest#test_exploit_rejects_parent_traversal",
    "Minitest::Assertion", "ArgumentError",
    "Exactly two Minitest probes in test/attachment_store_test.rb. Control: AttachmentStore.new(root).read(\"note.txt\") "
    "returns hello. Exploit: with secret.txt beside the root, read(\"../secret.txt\") raises ArgumentError with message "
    "outside root. AttachmentStore#read in lib/attachment_store.rb owns the containment check; the filesystem is a "
    "temporary directory and AttachmentStore is never stubbed.",
    "Attachment names from the download link reach AttachmentStore#read. A name such as ../secret.txt may resolve "
    "outside the attachment root and return another file.")

RUBY_ATTACH_HEAD = text("""
    require "fileutils"
    require "minitest/autorun"
    require "tmpdir"
    require_relative "../lib/attachment_store"

    class AttachmentStoreTest < Minitest::Test
      def setup
        @dir = Dir.mktmpdir
        @root = File.join(@dir, "attachments")
        Dir.mkdir(@root)
        File.write(File.join(@root, "note.txt"), "hello")
        File.write(File.join(@dir, "secret.txt"), "token")
      end

      def teardown
        FileUtils.remove_entry(@dir)
      end

      def test_control_reads_attachment
        assert_equal "hello", AttachmentStore.new(@root).read("note.txt")
      end
    """)

RUBY_REDIRECT = Scenario(
    "ruby", "open-redirect",
    (("lib/redirect_guard.rb", text("""
        # frozen_string_literal: true

        require "uri"

        module RedirectGuard
          def self.safe_target(target, allowed_hosts)
            uri = URI.parse(target)
            return target if uri.host.nil? && uri.scheme.nil? && target.start_with?("/") && !target.start_with?("//")
            return target if %w[http https].include?(uri.scheme) && allowed_hosts.include?(uri.host)

            "/"
          rescue URI::InvalidURIError
            "/"
          end
        end
        """)),),
    "test/redirect_guard_test.rb", "test/redirect_guard_test.rb::RedirectGuardTest#test_control_keeps_local_path",
    "test/redirect_guard_test.rb::RedirectGuardTest#test_exploit_redirects_external_host_to_root",
    "Minitest::Assertion", "redirect_to_root",
    "Exactly two Minitest probes in test/redirect_guard_test.rb. Control: RedirectGuard.safe_target(\"/account/settings\", "
    "[\"app.example\"]) returns the path unchanged. Exploit: safe_target(\"//evil.example/login\", [\"app.example\"]) "
    "returns /. RedirectGuard.safe_target in lib/redirect_guard.rb owns the decision.",
    "The return_to parameter after sign-in is passed to RedirectGuard.safe_target. A scheme-relative value such as "
    "//evil.example/login may send users to another host.")

RUBY_REDIRECT_HEAD = text("""
    require "minitest/autorun"
    require_relative "../lib/redirect_guard"

    class RedirectGuardTest < Minitest::Test
      ALLOWED = ["app.example"].freeze

      def test_control_keeps_local_path
        assert_equal "/account/settings", RedirectGuard.safe_target("/account/settings", ALLOWED)
      end
    """)

RUBY_AVATAR = Scenario(
    "ruby", "ssrf",
    (("lib/avatar_fetcher.rb", text("""
        # frozen_string_literal: true

        require "ipaddr"
        require "uri"

        class AvatarFetcher
          PRIVATE = %w[10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 127.0.0.0/8 169.254.0.0/16].map { |c| IPAddr.new(c) }

          def initialize(resolver:, http:)
            @resolver = resolver
            @http = http
          end

          def fetch(url)
            uri = URI.parse(url)
            address = IPAddr.new(@resolver.address_for(uri.host))
            raise ArgumentError, "private address" if PRIVATE.any? { |range| range.include?(address) }

            @http.get(uri)
          end
        end
        """)),),
    "test/avatar_fetcher_test.rb", "test/avatar_fetcher_test.rb::AvatarFetcherTest#test_control_fetches_public_avatar",
    "test/avatar_fetcher_test.rb::AvatarFetcherTest#test_exploit_rejects_metadata_address",
    "Minitest::Assertion", "ArgumentError",
    "Exactly two Minitest probes in test/avatar_fetcher_test.rb. Control: fetch https://cdn.example/a.png with a "
    "resolver double answering 203.0.113.10 and a recording HTTP double, and assert the returned body. Exploit: fetch "
    "http://metadata.internal/latest with the resolver answering 169.254.169.254, assert ArgumentError private "
    "address and assert the HTTP double received no request. AvatarFetcher#fetch owns the address check; the resolver "
    "and HTTP client are dependencies that may be doubled without deciding safety.",
    "Profile avatar URLs are fetched server-side by AvatarFetcher#fetch. A host that resolves to 169.254.169.254 may "
    "expose cloud instance metadata.")

RUBY_CONFIG = Scenario(
    "ruby", "unsafe-deserialization",
    (("lib/config_loader.rb", text("""
        # frozen_string_literal: true

        require "yaml"

        module ConfigLoader
          def self.load(text)
            YAML.safe_load(text, permitted_classes: [Symbol], aliases: false)
          end
        end
        """)),),
    "test/config_loader_test.rb", "test/config_loader_test.rb::ConfigLoaderTest#test_control_loads_plain_settings",
    "test/config_loader_test.rb::ConfigLoaderTest#test_exploit_rejects_ruby_object_tag",
    "Minitest::Assertion", "Psych::DisallowedClass",
    "Exactly two Minitest probes in test/config_loader_test.rb. Control: ConfigLoader.load(\"name: demo\\n\") returns "
    "{\"name\" => \"demo\"}. Exploit: loading a document tagged !ruby/object:OpenStruct raises Psych::DisallowedClass. "
    "ConfigLoader.load in lib/config_loader.rb owns the permitted-class policy.",
    "Imported project settings are read with ConfigLoader.load. A YAML document carrying a !ruby/object tag may "
    "instantiate arbitrary Ruby objects during import.")

RUBY_CONFIG_HEAD = text("""
    require "minitest/autorun"
    require_relative "../lib/config_loader"

    class ConfigLoaderTest < Minitest::Test
      PAYLOAD = "--- !ruby/object:OpenStruct\\ntable:\\n  name: demo\\n"
    """)

RUBY_AVATAR_DOUBLES = indent(text("""
      class StaticResolver
        def initialize(answers)
          @answers = answers
        end

        def address_for(host)
          @answers.fetch(host)
        end
      end

      class RecordingHttp
        attr_reader :requests

        def initialize
          @requests = []
        end

        def get(uri)
          @requests << uri.to_s
          "image-bytes"
        end
      end
    """), "  ")

RUBY = [
    Spec("ruby-valid-attachment-return-and-raise", RUBY_ATTACH, "minitest", RUBY_ATTACH_HEAD + text("""

          def test_exploit_rejects_parent_traversal
            error = assert_raises(ArgumentError) { AttachmentStore.new(@root).read("../secret.txt") }
            assert_equal "outside root", error.message
          end
        end
        """),
         ("assert_raises(ArgumentError)",), VALID,
         "Real AttachmentStore seam: the control returns file content and the exploit asserts the specific "
         "ArgumentError from production containment.", kind="positive"),
    Spec("ruby-valid-resolver-and-http-doubles", RUBY_AVATAR, "minitest", text("""
        require "minitest/autorun"
        require_relative "../lib/avatar_fetcher"

        class AvatarFetcherTest < Minitest::Test
        """) + RUBY_AVATAR_DOUBLES + text("""

          def test_control_fetches_public_avatar
            http = RecordingHttp.new
            fetcher = AvatarFetcher.new(resolver: StaticResolver.new("cdn.example" => "203.0.113.10"), http: http)
            assert_equal "image-bytes", fetcher.fetch("https://cdn.example/a.png")
          end

          def test_exploit_rejects_metadata_address
            http = RecordingHttp.new
            resolver = StaticResolver.new("metadata.internal" => "169.254.169.254")
            fetcher = AvatarFetcher.new(resolver: resolver, http: http)
            error = assert_raises(ArgumentError) { fetcher.fetch("http://metadata.internal/latest") }
            assert_equal "private address", error.message
            assert_empty http.requests
          end
        end
        """),
         ("assert_raises(ArgumentError)", "assert_empty http.requests"), VALID,
         "Resolver and HTTP doubles only answer and record; production AvatarFetcher still owns the private-address "
         "check the exploit asserts.", kind="positive"),
    Spec("ruby-copied-redirect-guard", RUBY_REDIRECT, "minitest", text("""
        require "minitest/autorun"
        require "uri"

        class RedirectGuardTest < Minitest::Test
          ALLOWED = ["app.example"].freeze

          def safe_target(target, allowed_hosts)
            uri = URI.parse(target)
            return target if uri.host.nil? && uri.scheme.nil? && target.start_with?("/") && !target.start_with?("//")
            return target if %w[http https].include?(uri.scheme) && allowed_hosts.include?(uri.host)

            "/"
          rescue URI::InvalidURIError
            "/"
          end

          def test_control_keeps_local_path
            assert_equal "/account/settings", safe_target("/account/settings", ALLOWED)
          end

          def test_exploit_redirects_external_host_to_root
            assert_equal "/", safe_target("//evil.example/login", ALLOWED)
          end
        end
        """), ('assert_equal "/", safe_target',), {"source_linked": False},
         "The test class defines its own safe_target with the guard's logic and never loads lib/redirect_guard.rb."),
    Spec("ruby-minitest-stub-on-target-method", RUBY_ATTACH, "minitest", RUBY_ATTACH_HEAD.replace(
        'require "minitest/autorun"\n', 'require "minitest/autorun"\nrequire "minitest/mock"\n') + text("""

          def test_exploit_rejects_parent_traversal
            store = AttachmentStore.new(@root)
            guarded = ->(name) { name.include?("..") ? raise(ArgumentError, "outside root") : "hello" }
            store.stub(:read, guarded) do
              error = assert_raises(ArgumentError) { store.read("../secret.txt") }
              assert_equal "outside root", error.message
            end
          end
        end
        """),
         ("assert_raises(ArgumentError)",), {"source_linked": False},
         "The exploit stubs AttachmentStore#read on the instance under test with a lambda, so the asserted "
         "ArgumentError comes from the stub, not production containment."),
    Spec("ruby-vacuous-yaml-assertions", RUBY_CONFIG, "minitest", RUBY_CONFIG_HEAD + text("""

          def test_control_loads_plain_settings
            ConfigLoader.load("name: demo\\n")
            assert true
          end

          def test_exploit_rejects_ruby_object_tag
            ConfigLoader.load(PAYLOAD)
          rescue StandardError
            nil
          ensure
            refute_nil ConfigLoader
          end
        end
        """),
         ("refute_nil ConfigLoader",), {"assertions_relevant": False},
         "Both probes call the real ConfigLoader with the right inputs, but the assertions are constants that hold "
         "whatever load does."),
    Spec("ruby-resolver-double-owns-address-check", RUBY_AVATAR, "minitest", text("""
        require "minitest/autorun"
        require_relative "../lib/avatar_fetcher"

        class AvatarFetcherTest < Minitest::Test
          class FilteringResolver
            def address_for(host)
              raise ArgumentError, "private address" if host.end_with?(".internal")

              "203.0.113.10"
            end
          end

          class StaticHttp
            def get(_uri)
              "image-bytes"
            end
          end

          def test_control_fetches_public_avatar
            fetcher = AvatarFetcher.new(resolver: FilteringResolver.new, http: StaticHttp.new)
            assert_equal "image-bytes", fetcher.fetch("https://cdn.example/a.png")
          end

          def test_exploit_rejects_metadata_address
            fetcher = AvatarFetcher.new(resolver: FilteringResolver.new, http: StaticHttp.new)
            error = assert_raises(ArgumentError) { fetcher.fetch("http://metadata.internal/latest") }
            assert_equal "private address", error.message
          end
        end
        """), ("assert_raises(ArgumentError)",), {"dependency_scope_valid": False},
         "The resolver double raises the private-address error by host name, so the rejection is decided by the "
         "double and AvatarFetcher's address check never runs."),
    Spec("ruby-legacy-redirect-module", RUBY_REDIRECT, "minitest", text("""
        require "minitest/autorun"
        require_relative "../lib/legacy_redirect"

        class RedirectGuardTest < Minitest::Test
          ALLOWED = ["app.example"].freeze

          def test_control_keeps_local_path
            assert_equal "/account/settings", LegacyRedirect.safe_target("/account/settings", ALLOWED)
          end

          def test_exploit_redirects_external_host_to_root
            assert_equal "/", LegacyRedirect.safe_target("//evil.example/login", ALLOWED)
          end
        end
        """), ('assert_equal "/", LegacyRedirect',), {"source_linked": False},
         "The probes load lib/legacy_redirect.rb and call LegacyRedirect.safe_target, a different module, instead of "
         "RedirectGuard.safe_target named by the plan.",
         extra_sources=(("lib/legacy_redirect.rb", text("""
            # frozen_string_literal: true

            module LegacyRedirect
              def self.safe_target(target, _allowed_hosts)
                return "/" if target.start_with?("//") || target.match?(%r{\\Ahttps?://})

                target
              end
            end
            """)),)),
    Spec("ruby-benign-yaml-for-exploit", RUBY_CONFIG, "minitest", RUBY_CONFIG_HEAD + text("""

          def test_control_loads_plain_settings
            assert_equal({ "name" => "demo" }, ConfigLoader.load("name: demo\\n"))
          end

          def test_exploit_rejects_ruby_object_tag
            assert_raises(Psych::DisallowedClass) { ConfigLoader.load("name: demo\\n") }
          end
        end
        """),
         ("assert_raises(Psych::DisallowedClass)",), {"condition_exercised": False},
         "The exploit expects Psych::DisallowedClass but loads the same plain document as the control; the tagged "
         "payload it declares is never used."),
    Spec("ruby-unrelated-allowlist-assertion", RUBY_REDIRECT, "minitest", RUBY_REDIRECT_HEAD + text("""

          def test_exploit_redirects_external_host_to_root
            allowed = ["app.example"]
            RedirectGuard.safe_target("//evil.example/login", allowed)
            assert_equal ["app.example"], allowed
          end
        end
        """),
         ('assert_equal ["app.example"], allowed',), {"assertions_relevant": False},
         "The exploit passes the scheme-relative URL to the real guard but asserts only that its allow-list argument "
         "was not modified, ignoring the returned target."),
    Spec("ruby-exploit-only-flunks-on-raise", RUBY_REDIRECT, "minitest", RUBY_REDIRECT_HEAD + text("""

          def test_exploit_redirects_external_host_to_root
            RedirectGuard.safe_target("//evil.example/login", ALLOWED)
          rescue StandardError => e
            flunk "safe_target raised #{e.class}"
          end
        end
        """),
         ('flunk "safe_target raised',), {"assertions_relevant": False},
         "The open-redirect exploit only fails if safe_target raises; it never checks the returned target."),
    Spec("ruby-skip-before-attachment-exploit", RUBY_ATTACH, "minitest", RUBY_ATTACH_HEAD + text("""

          def test_exploit_rejects_parent_traversal
            skip "requires the shared attachment volume" unless ENV["SHARED_ATTACHMENTS"]
            error = assert_raises(ArgumentError) { AttachmentStore.new(@root).read("../secret.txt") }
            assert_equal "outside root", error.message
          end
        end
        """),
         ("assert_raises(ArgumentError)",), {"condition_exercised": False},
         "The exploit skips unless an environment variable the plan never sets is present, so the traversal input "
         "is not exercised."),
]

# ----------------------------------------------------------------------------------------------- Perl (Test::More, TAP)

# The TAP runner classifies a failed subtest without an exception type (only a died subtest is `die`, as an error),
# so no token matches a TAP assertion failure; this one names the native failure for the plan's required field.
TAP_FAILURE = "Test::More::not_ok"

PERL_FILES = Scenario(
    "perl", "path-traversal",
    (("lib/My/Files.pm", text("""
        package My::Files;
        use strict;
        use warnings;
        use Cwd qw(realpath);
        use File::Spec;
        use Exporter 'import';
        our @EXPORT_OK = qw(read_file);

        sub read_file {
            my ($root, $name) = @_;
            my $base = realpath($root);
            my $path = realpath(File::Spec->catfile($base, $name));
            die "outside root\\n" unless defined $path && index($path, "$base/") == 0;
            open my $fh, '<', $path or die "cannot open: $!\\n";
            local $/;
            return scalar <$fh>;
        }

        1;
        """)),),
    "t/files.t", "t/files.t#control_reads_document", "t/files.t#exploit_rejects_parent_traversal",
    TAP_FAILURE, "die",
    "Exactly two Test::More subtests in t/files.t. Control: read_file(\"$dir/docs\", 'note.txt') returns hello. "
    "Exploit: with secret.txt beside the root, read_file(\"$dir/docs\", '../secret.txt') dies and $@ matches "
    "outside root. My::Files::read_file in lib/My/Files.pm owns the containment check; the filesystem is a temporary "
    "directory and read_file is never redefined.",
    "File names from the download handler reach My::Files::read_file. A name such as ../secret.txt may resolve "
    "outside the document root and return another file.")

PERL_FILES_HEAD = text("""
    use strict;
    use warnings;
    use Test::More;
    use File::Temp qw(tempdir);
    use lib 'lib';
    use My::Files qw(read_file);

    my $dir = tempdir(CLEANUP => 1);
    mkdir "$dir/docs" or die $!;
    open my $note, '>', "$dir/docs/note.txt" or die $!;
    print {$note} 'hello';
    close $note;
    open my $secret, '>', "$dir/secret.txt" or die $!;
    print {$secret} 'token';
    close $secret;

    subtest control_reads_document => sub {
        is(read_file("$dir/docs", 'note.txt'), 'hello', 'reads file inside root');
    };
    """)

PERL_FILES_EXPLOIT = text("""
        my $ok = eval { read_file("$dir/docs", '../secret.txt'); 1 };
        ok(!$ok, 'parent traversal is refused');
        like($@, qr/^outside root/, 'refusal comes from root containment');
    };

    done_testing;
    """)

PERL_REPORT = Scenario(
    "perl", "command-injection",
    (("lib/My/Report.pm", text("""
        package My::Report;
        use strict;
        use warnings;

        sub new {
            my ($class, %args) = @_;
            my $runner = $args{runner} || sub { system { $_[0] } @_ };
            return bless { runner => $runner }, $class;
        }

        sub archive {
            my ($self, $name) = @_;
            my @command = ('tar', '-czf', "$name.tgz", 'reports');
            $self->{runner}->(@command);
            return \\@command;
        }

        1;
        """)),),
    "t/report.t", "t/report.t#control_archives_named_report", "t/report.t#exploit_keeps_name_single_argument",
    TAP_FAILURE, "single_argument",
    "Exactly two Test::More subtests in t/report.t. Control: archive weekly with a recording runner and assert the "
    "runner received exactly (tar, -czf, weekly.tgz, reports). Exploit: archive 'weekly; touch /tmp/pwned' and assert "
    "the runner received the whole name as one argument, (tar, -czf, 'weekly; touch /tmp/pwned.tgz', reports), so no "
    "shell parses it. My::Report::archive owns command construction; only the runner (process execution) may be "
    "replaced, by a recorder that does not decide safety.",
    "Report names from the export form reach My::Report::archive. A name such as weekly; touch /tmp/pwned could run "
    "an extra command if the archive command went through a shell.")

PERL_REPORT_HEAD = text("""
    use strict;
    use warnings;
    use Test::More;
    use lib 'lib';
    use My::Report;

    sub recorder {
        my $calls = shift;
        return sub { push @{$calls}, [@_]; return 0 };
    }

    subtest control_archives_named_report => sub {
        my @calls;
        My::Report->new(runner => recorder(\\@calls))->archive('weekly');
        is_deeply(\\@calls, [['tar', '-czf', 'weekly.tgz', 'reports']], 'tar invoked with list arguments');
    };
    """)

PERL_VIEW = Scenario(
    "perl", "xss",
    (("lib/My/View.pm", text("""
        package My::View;
        use strict;
        use warnings;
        use Exporter 'import';
        our @EXPORT_OK = qw(render_comment);

        my %ESCAPE = ('&' => '&amp;', '<' => '&lt;', '>' => '&gt;', '"' => '&quot;', "'" => '&#39;');

        sub render_comment {
            my ($text) = @_;
            (my $safe = $text) =~ s/([&<>"'])/$ESCAPE{$1}/g;
            return qq{<p class="comment">$safe</p>};
        }

        1;
        """)),),
    "t/view.t", "t/view.t#control_renders_plain_comment", "t/view.t#exploit_escapes_script_tag",
    TAP_FAILURE, "html_escaped",
    "Exactly two Test::More subtests in t/view.t. Control: render_comment('hello') returns "
    "<p class=\"comment\">hello</p>. Exploit: render_comment('<script>alert(1)</script>') returns exactly "
    "<p class=\"comment\">&lt;script&gt;alert(1)&lt;/script&gt;</p>, with no raw script tag. "
    "My::View::render_comment in lib/My/View.pm owns escaping.",
    "Comment bodies are rendered with My::View::render_comment. A body containing <script>alert(1)</script> may run "
    "script in other readers' browsers.")

PERL_VIEW_HEAD = text("""
    use strict;
    use warnings;
    use Test::More;
    use lib 'lib';
    use My::View qw(render_comment);

    subtest control_renders_plain_comment => sub {
        is(render_comment('hello'), '<p class="comment">hello</p>', 'plain text unchanged');
    };
    """)

PERL = [
    Spec("perl-valid-files-return-and-die", PERL_FILES, "test-more", PERL_FILES_HEAD + text("""

        subtest exploit_rejects_parent_traversal => sub {
        """) + PERL_FILES_EXPLOIT,
         ("ok(!$ok, 'parent traversal is refused');", "like($@, qr/^outside root/"), VALID,
         "Real My::Files seam: the control returns file content and the exploit asserts the specific die message "
         "from production containment.", kind="positive"),
    Spec("perl-valid-recording-runner", PERL_REPORT, "test-more", PERL_REPORT_HEAD + text("""

        subtest exploit_keeps_name_single_argument => sub {
            my @calls;
            my $name = 'weekly; touch /tmp/pwned';
            My::Report->new(runner => recorder(\\@calls))->archive($name);
            is_deeply(\\@calls, [['tar', '-czf', "$name.tgz", 'reports']], 'name stays one argument');
        };

        done_testing;
        """), ("'name stays one argument'",), VALID,
         "A recording runner only replaces process execution; production My::Report::archive still builds the list "
         "command whose single-argument shape the exploit asserts.", kind="positive"),
    Spec("perl-copied-read-file-sub", PERL_FILES, "test-more", PERL_FILES_HEAD.replace(
        "use My::Files qw(read_file);\n", "use Cwd qw(realpath);\nuse File::Spec;\n").replace(
        "my $dir = tempdir", text("""
            sub read_file {
                my ($root, $name) = @_;
                my $base = realpath($root);
                my $path = realpath(File::Spec->catfile($base, $name));
                die "outside root\\n" unless defined $path && index($path, "$base/") == 0;
                open my $fh, '<', $path or die "cannot open: $!\\n";
                local $/;
                return scalar <$fh>;
            }

            my $dir = tempdir""")) + text("""

        subtest exploit_rejects_parent_traversal => sub {
        """) + PERL_FILES_EXPLOIT,
         ("ok(!$ok, 'parent traversal is refused');", "like($@, qr/^outside root/"), {"source_linked": False},
         "The test file declares its own read_file with the containment logic and never loads My::Files."),
    Spec("perl-local-override-of-target-sub", PERL_FILES, "test-more", PERL_FILES_HEAD + text("""

        subtest exploit_rejects_parent_traversal => sub {
            no warnings 'redefine';
            local *My::Files::read_file = sub {
                my ($root, $name) = @_;
                die "outside root\\n" if $name =~ /\\.\\./;
                return 'hello';
            };
            my $ok = eval { My::Files::read_file("$dir/docs", '../secret.txt'); 1 };
            ok(!$ok, 'parent traversal is refused');
            like($@, qr/^outside root/, 'refusal comes from root containment');
        };

        done_testing;
        """), ("ok(!$ok, 'parent traversal is refused');", "like($@, qr/^outside root/"), {"source_linked": False},
         "The exploit locally redefines My::Files::read_file with a stand-in that dies on .., so the asserted refusal "
         "comes from the override."),
    Spec("perl-vacuous-view-assertions", PERL_VIEW, "test-more", text("""
        use strict;
        use warnings;
        use Test::More;
        use lib 'lib';
        use My::View qw(render_comment);

        subtest control_renders_plain_comment => sub {
            render_comment('hello');
            pass('rendered');
        };

        subtest exploit_escapes_script_tag => sub {
            my $html = render_comment('<script>alert(1)</script>');
            ok(1, 'rendered comment');
        };

        done_testing;
        """), ("ok(1, 'rendered comment');",), {"assertions_relevant": False},
         "Both subtests call the real render_comment with the right inputs, but pass and ok(1) hold whatever it "
         "returns."),
    Spec("perl-runner-double-owns-refusal", PERL_REPORT, "test-more", text("""
        use strict;
        use warnings;
        use Test::More;
        use lib 'lib';
        use My::Report;

        sub refusing_runner {
            return sub {
                die "shell metacharacter\\n" if grep { /[;&|`\\$]/ } @_;
                return 0;
            };
        }

        subtest control_archives_named_report => sub {
            my $command = My::Report->new(runner => refusing_runner())->archive('weekly');
            is_deeply($command, ['tar', '-czf', 'weekly.tgz', 'reports'], 'tar invoked with list arguments');
        };

        subtest exploit_keeps_name_single_argument => sub {
            my $ok = eval { My::Report->new(runner => refusing_runner())->archive('weekly; touch /tmp/pwned'); 1 };
            ok(!$ok, 'unsafe name refused');
            like($@, qr/shell metacharacter/, 'refused before execution');
        };

        done_testing;
        """), ("ok(!$ok, 'unsafe name refused');", "like($@, qr/shell metacharacter/"),
         {"dependency_scope_valid": False},
         "The runner double refuses shell metacharacters itself, so the exploit asserts a refusal the production "
         "archive code never makes."),
    Spec("perl-legacy-files-package", PERL_FILES, "test-more", PERL_FILES_HEAD.replace(
        "use My::Files qw(read_file);", "use My::LegacyFiles;").replace(
        "is(read_file(", "is(My::LegacyFiles::slurp(") + text("""

        subtest exploit_rejects_parent_traversal => sub {
            my $ok = eval { My::LegacyFiles::slurp("$dir/docs", '../secret.txt'); 1 };
            ok(!$ok, 'parent traversal is refused');
            like($@, qr/^outside root/, 'refusal comes from root containment');
        };

        done_testing;
        """), ("ok(!$ok, 'parent traversal is refused');", "like($@, qr/^outside root/"), {"source_linked": False},
         "The subtests call My::LegacyFiles::slurp, a different package with its own check, instead of "
         "My::Files::read_file named by the plan.",
         extra_sources=(("lib/My/LegacyFiles.pm", text("""
            package My::LegacyFiles;
            use strict;
            use warnings;

            sub slurp {
                my ($root, $name) = @_;
                die "outside root\\n" if $name =~ m{(?:^|/)\\.\\.(?:/|$)};
                open my $fh, '<', "$root/$name" or die "cannot open: $!\\n";
                local $/;
                return scalar <$fh>;
            }

            1;
            """)),)),
    Spec("perl-benign-name-for-exploit", PERL_REPORT, "test-more", PERL_REPORT_HEAD + text("""

        subtest exploit_keeps_name_single_argument => sub {
            my @calls;
            my $name = 'weekly';
            My::Report->new(runner => recorder(\\@calls))->archive($name);
            is_deeply(\\@calls, [['tar', '-czf', "$name.tgz", 'reports']], 'name stays one argument');
        };

        done_testing;
        """), ("'name stays one argument'",), {"condition_exercised": False},
         "The exploit asserts the single-argument command shape but archives the benign control name instead of the "
         "shell payload."),
    Spec("perl-unrelated-wrapper-assertion", PERL_VIEW, "test-more", PERL_VIEW_HEAD + text("""

        subtest exploit_escapes_script_tag => sub {
            my $html = render_comment('<script>alert(1)</script>');
            like($html, qr/^<p class="comment">/, 'comment wrapper present');
        };

        done_testing;
        """), ("'comment wrapper present'",), {"assertions_relevant": False},
         "The XSS exploit renders the payload through the real view but asserts only the surrounding paragraph "
         "markup, which is present whether or not the body is escaped."),
    Spec("perl-exploit-asserts-only-lives", PERL_VIEW, "test-more", PERL_VIEW_HEAD + text("""

        subtest exploit_escapes_script_tag => sub {
            ok(eval { render_comment('<script>alert(1)</script>'); 1 }, 'renders without dying');
        };

        done_testing;
        """), ("'renders without dying'",), {"assertions_relevant": False},
         "The exploit asserts only that render_comment does not die on the script payload, not what it returns."),
    Spec("perl-skip-all-before-traversal", PERL_FILES, "test-more", PERL_FILES_HEAD + text("""

        subtest exploit_rejects_parent_traversal => sub {
            plan skip_all => 'shared document volume not mounted' unless $ENV{SHARED_DOCS};
        """) + PERL_FILES_EXPLOIT,
         ("ok(!$ok, 'parent traversal is refused');", "like($@, qr/^outside root/"), {"condition_exercised": False},
         "The exploit subtest skips unless an environment variable the plan never sets is present, so the traversal "
         "input is not exercised."),
]

SPECS = JAVA + JAVASCRIPT + RUBY + PERL


def render() -> dict[str, dict[str, str]]:
    names = [spec.name for spec in SPECS]
    if len(set(names)) != len(names):
        raise ValueError("duplicate case id")
    return {spec.name: {part: json.dumps(value, indent=2, ensure_ascii=False) + "\n"
                        for part, value in build(spec).items()} for spec in SPECS}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="compare with cases/ without writing")
    args = parser.parse_args()
    differing = []
    for name, parts in render().items():
        for part, content in parts.items():
            path = CASES / name / f"{part}.json"
            if args.check:
                if not path.exists() or path.read_text() != content:
                    differing.append(str(path))
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)
    if differing:
        print("\n".join(differing))
        sys.exit(1)
    print(f"{len(SPECS)} breadth cases {'match' if args.check else 'written'}")


if __name__ == "__main__":
    main()
