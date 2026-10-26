# Trusted runtime only.  Target source is bind-mounted read-only at /source.
#
# The base image digest is a supply-chain pin, not the runtime identity admitted for an
# evidence run: DockerSandbox.image_id resolves this tag to Docker's immutable local
# image ID and the manifest records that ID.  JUnit and JaCoCo are vendored at build
# time with pinned versions and verified SHA-256 checksums; there is no network at run
# time.  Rebuild with `just images` after changing this file or the driver.
FROM eclipse-temurin:21-jdk-jammy@sha256:742daacb9316be4b6fc60258f6e4ac2a11882f6c597373c92290a57bfad0d2e0

ARG JUNIT_VERSION=1.11.4
ARG JACOCO_VERSION=0.8.12
ARG JUNIT_SHA256=b016ef6b1c3454d6d7c2c88ce081dabf289699686af6622d6e4e2e1b54b4a2fc
ARG JACOCO_SHA256=35cf2a2b8937659ecbc8d0d3902dfa7f55b7ed2250e82424036a3e1d12462cd7

# jq parses the operator job JSON and builds the strict record; libxml2-utils (xmllint)
# reads the JUnit and JaCoCo XML reports.  curl and unzip are only used at build time.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        jq libxml2-utils curl unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN set -eu; \
    mkdir -p /opt/corsair /opt/build; \
    curl -fsSL -o /opt/build/junit-standalone.jar \
        "https://repo1.maven.org/maven2/org/junit/platform/junit-platform-console-standalone/${JUNIT_VERSION}/junit-platform-console-standalone-${JUNIT_VERSION}.jar"; \
    echo "${JUNIT_SHA256}  /opt/build/junit-standalone.jar" | sha256sum -c -; \
    curl -fsSL -o /opt/build/jacoco.zip \
        "https://repo1.maven.org/maven2/org/jacoco/jacoco/${JACOCO_VERSION}/jacoco-${JACOCO_VERSION}.zip"; \
    echo "${JACOCO_SHA256}  /opt/build/jacoco.zip" | sha256sum -c -; \
    unzip -j -o /opt/build/jacoco.zip 'lib/jacocoagent.jar' 'lib/jacococli.jar' -d /opt/corsair; \
    cp /opt/build/junit-standalone.jar /opt/corsair/junit-standalone.jar; \
    rm -rf /opt/build; \
    groupadd --gid 1000 corsair; \
    useradd --uid 1000 --gid 1000 --create-home --home-dir /home/corsair --shell /usr/sbin/nologin corsair; \
    mkdir -p /work /tmp; \
    chown -R 1000:1000 /work /tmp /home/corsair; \
    chmod 0555 /opt/corsair; \
    chmod 0444 /opt/corsair/*.jar

COPY --chmod=0555 src/corsair/adapters/sandboxing/drivers/java/driver.sh /opt/corsair/driver.sh

# DockerSandbox additionally enforces read_only, no-new-privileges, cap_drop=ALL,
# network_mode=none, PID/CPU/memory limits, and read-only fixture/source/job binds.
USER 1000:1000
WORKDIR /work
ENTRYPOINT ["bash", "/opt/corsair/driver.sh"]
