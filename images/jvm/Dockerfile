# JVM probe image: Maven/JDK plus Gradle and a reviewed offline JaCoCo CLI/agent for native target coverage.
FROM docker.io/library/maven:3.9.11-eclipse-temurin-21

USER root
ENV DEBIAN_FRONTEND=noninteractive PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 HOME=/tmp
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl python3 python3-pip unzip \
    && python3 -m pip install --break-system-packages pytest==9.0.3 coverage==7.13.4 \
    && rm -rf /var/lib/apt/lists/*

# Gradle is installed at build time, never fetched by an offline probe.
RUN curl --fail --location --proto '=https' --tlsv1.2 --retry 3 -o /tmp/gradle.zip \
        https://services.gradle.org/distributions/gradle-8.14.3-bin.zip \
    && echo 'bd71102213493060956ec229d946beee57158dbd89d0e62b91bca0fa2c5f3531  /tmp/gradle.zip' | sha256sum -c - \
    && unzip -q /tmp/gradle.zip -d /opt \
    && ln -s /opt/gradle-8.14.3/bin/gradle /usr/local/bin/gradle \
    && rm /tmp/gradle.zip

# Both artifacts come from the single pinned JaCoCo 0.8.13 distribution and are verified before installation.
RUN curl --fail --location --proto '=https' --tlsv1.2 --retry 3 -o /tmp/jacoco.zip \
        https://repo1.maven.org/maven2/org/jacoco/jacoco/0.8.13/jacoco-0.8.13.zip \
    && echo '96586427ed734138ca4867ca2ceeb70c27e856a113638ea41709ec0734147c60  /tmp/jacoco.zip' | sha256sum -c - \
    && unzip -q /tmp/jacoco.zip lib/jacocoagent.jar lib/jacococli.jar -d /opt/corsair \
    && mv /opt/corsair/lib /opt/corsair/jacoco \
    && rm /tmp/jacoco.zip \
    && echo '47e700ccb0fdb9e27c5241353f8161938f4e53c3561dd35e063c5fe88dc3349b  /opt/corsair/jacoco/jacocoagent.jar' | sha256sum -c - \
    && echo '8f748683833d4dc4d72cea5d6b43f49344687b831e0582c97bcb9b984e3de0a3  /opt/corsair/jacoco/jacococli.jar' | sha256sum -c -

RUN (getent group 1000 || groupadd --gid 1000 corsair) \
    && (getent passwd 1000 || useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin corsair) \
    && mkdir -p /work && ln -s /usr/bin/python3 /usr/local/bin/python
WORKDIR /work
# Build as root; DockerSandboxes always opens offline probes as 1000:1000.
