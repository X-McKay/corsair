# Trusted JDK-only observer. Target source is bind-mounted read-only at /source.
FROM eclipse-temurin:21-jdk-jammy@sha256:742daacb9316be4b6fc60258f6e4ac2a11882f6c597373c92290a57bfad0d2e0

# The base reference is Eclipse Temurin's published multi-architecture index digest. The JDK-only
# downloader below verifies native observer dependencies against publisher hashes before use.
RUN mkdir -p /opt/corsair/lib /opt/corsair/classes /work /tmp \
    && chown -R 10001:10001 /work /tmp

COPY src/corsair/adapters/sandboxing/java/PinnedDownloader.java /tmp/PinnedDownloader.java
RUN javac -proc:none -g -d /tmp /tmp/PinnedDownloader.java \
    && java -cp /tmp PinnedDownloader SHA-512 \
      https://repo.maven.apache.org/maven2/org/junit/platform/junit-platform-console-standalone/6.1.3/junit-platform-console-standalone-6.1.3.jar \
      ba9f93c8e45cba7231e4af859152cc6410684d56814768efee868eca8e27c7f01a28ffd1add0e13e4f675dcf0a9f01b235a949040f390c75d8269bf07eab8a79 \
      /opt/corsair/lib/junit-platform-console-standalone.jar \
    && java -cp /tmp PinnedDownloader SHA-256 \
      https://search.maven.org/remotecontent?filepath=org/jacoco/jacoco/0.8.15/jacoco-0.8.15.zip \
      5b3f6ddb724e761d25c937d68b0189a3a23f3e220e3282575ee0b53359e8110e \
      /tmp/jacoco-0.8.15.zip \
    && mkdir /tmp/jacoco \
    && (cd /tmp/jacoco && jar xf /tmp/jacoco-0.8.15.zip lib/jacocoagent.jar lib/jacococli.jar) \
    && mv /tmp/jacoco/lib/jacocoagent.jar /opt/corsair/lib/jacocoagent.jar \
    && mv /tmp/jacoco/lib/jacococli.jar /opt/corsair/lib/jacococli.jar \
    && java -cp /tmp PinnedDownloader SHA-512 \
      https://repo.maven.apache.org/maven2/com/fasterxml/jackson/core/jackson-annotations/2.22/jackson-annotations-2.22.jar \
      63b597ec02b4e31c57266d9b96f05f301f217bc12ffb7ba046a5658d2829728930a559947b98eb6c3cc448413a96b4939427aa669ae1e2dc3597ab5d5d287f9f \
      /opt/corsair/lib/jackson-annotations.jar \
    && java -cp /tmp PinnedDownloader SHA-512 \
      https://repo.maven.apache.org/maven2/com/fasterxml/jackson/core/jackson-core/2.22.4/jackson-core-2.22.4.jar \
      3b0d500043699ce40fc6befc04c9dbf3e8067de453098fba53d1891793bd3da80955e44536d113fac6fc8fb58264e47b265ab3466b3c6fd4bca111487ac24700 \
      /opt/corsair/lib/jackson-core.jar \
    && java -cp /tmp PinnedDownloader SHA-512 \
      https://repo.maven.apache.org/maven2/com/fasterxml/jackson/core/jackson-databind/2.22.4/jackson-databind-2.22.4.jar \
      688ee3a248895070623288bbbd1050e1c14f54d24ddac9be1e624e264eed8d88a6ca07ae90af6056bed1e5f1d0c9ac9db503cbcaaa45db7ba8ca213d3387dde6 \
      /opt/corsair/lib/jackson-databind.jar \
    && rm -rf /tmp/PinnedDownloader.java /tmp/PinnedDownloader.class /tmp/jacoco /tmp/jacoco-0.8.15.zip

COPY src/corsair/adapters/sandboxing/java/Driver.java /opt/corsair/Driver.java
COPY src/corsair/adapters/sandboxing/java/SecretDisclosureProbe.java /opt/corsair/SecretDisclosureProbe.java
RUN javac -proc:none -g -cp '/opt/corsair/lib/*' -d /opt/corsair/classes \
      /opt/corsair/Driver.java /opt/corsair/SecretDisclosureProbe.java \
    && rm /opt/corsair/Driver.java /opt/corsair/SecretDisclosureProbe.java \
    && chown -R root:root /opt/corsair \
    && chmod -R a+rX /opt/corsair \
    && chmod -R a-w /opt/corsair

# DockerSandbox additionally enforces read_only, no-new-privileges, cap_drop=ALL,
# network_mode=none, 512m/1CPU/64pid limits, and read-only fixture/source/job binds.
USER 10001:10001
WORKDIR /work
ENTRYPOINT ["java", "-cp", "/opt/corsair/classes:/opt/corsair/lib/*", "corsair.sandboxing.java.Driver"]
