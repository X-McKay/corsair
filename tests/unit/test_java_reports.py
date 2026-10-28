from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "deploy" / "java" / "Dockerfile"
DRIVER = ROOT / "src" / "corsair" / "adapters" / "sandboxing" / "java" / "Driver.java"
PROBE = ROOT / "src" / "corsair" / "adapters" / "sandboxing" / "java" / "SecretDisclosureProbe.java"
DOWNLOADER = ROOT / "src" / "corsair" / "adapters" / "sandboxing" / "java" / "PinnedDownloader.java"


def test_java_image_pins_a_multiarch_jdk_and_native_observer_dependencies() -> None:
    source = DOCKERFILE.read_text(encoding="utf-8")

    assert (
        "eclipse-temurin:21-jdk-jammy@sha256:"
        "742daacb9316be4b6fc60258f6e4ac2a11882f6c597373c92290a57bfad0d2e0"
    ) in source
    assert "junit-platform-console-standalone/6.1.3" in source
    assert "jacoco-0.8.15.zip" in source
    assert "5b3f6ddb724e761d25c937d68b0189a3a23f3e220e3282575ee0b53359e8110e" in source
    assert "jackson-databind/2.22.4" in source
    assert "jackson-core/2.22.4" in source
    assert "jackson-annotations/2.22" in source
    assert "Maven" not in source
    assert "Gradle" not in source
    assert source.count("-proc:none") >= 2
    assert "USER 10001:10001" in source


def test_java_driver_projects_only_complete_native_reports_to_held_or_violation() -> None:
    source = DRIVER.read_text(encoding="utf-8")

    assert 'static final String SCHEMA_VERSION = "corsair.driver/1"' in source
    assert 'static final String JOB_SCHEMA_VERSION = "corsair.driver-job/1"' in source
    assert '"native_exit_code", exitCode' in source
    assert '"native_reports", nativeReports' in source
    assert "if (report.valid() && !coveredLines.isEmpty())" in source
    assert 'outcome = "PROPERTY_HELD"' in source
    assert 'outcome = "VIOLATION"' in source
    assert 'outcome = "INVALID"' in source
    assert 'outcome = "ERROR"' in source
    assert "DocumentBuilderFactory.newInstance()" in source
    assert 'load-external-dtd", false' in source
    assert "ACCESS_EXTERNAL_DTD" in source
    assert "ACCESS_EXTERNAL_SCHEMA" in source
    assert '"javac"' in source
    assert '"-proc:none"' in source
    assert '"-g"' in source


def test_java_probe_uses_fixed_string_assertions_without_private_fixture_diagnostics() -> None:
    source = PROBE.read_text(encoding="utf-8")

    assert 'Path.of("/fixtures/private/secret.txt")' in source
    assert "secret.equals(invocation.result())" in source
    assert "Driver.DISCLOSURE_FAILURE" in source
    assert "Driver.CONTROL_FAILURE" in source
    assert "Driver.EXECUTION_FAILURE" in source
    assert "System.setOut(replacement)" in source
    assert "System.out.write" not in source


def test_build_time_downloader_verifies_a_digest_before_installing_dependencies() -> None:
    source = DOWNLOADER.read_text(encoding="utf-8")

    assert "MessageDigest.getInstance(algorithm)" in source
    assert "MessageDigest.isEqual(expected, digest.digest())" in source
    assert "HttpClient.Redirect.NORMAL" in source
    assert "ATOMIC_MOVE" in source


def test_java_runtime_dependencies_are_readable_but_not_writable_by_sandbox_user():
    source = DOCKERFILE.read_text()
    assert "chmod -R a+rX /opt/corsair" in source
    assert "chmod -R a-w /opt/corsair" in source
    driver = DRIVER.read_text()
    assert "redirectInput(ProcessBuilder.Redirect.DISCARD)" not in driver
    assert 'LIBRARY.resolve("jackson-databind.jar")' in driver
