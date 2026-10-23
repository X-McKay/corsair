# Digest-pinned Java 21 runtime plus pinned JaCoCo agent/CLI for native line evidence.
FROM docker.io/library/eclipse-temurin@sha256:742daacb9316be4b6fc60258f6e4ac2a11882f6c597373c92290a57bfad0d2e0
ARG JACOCO_VERSION=0.8.14
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export CURL_CA_BUNDLE=/run/secrets/proxy_ca; fi; \
    mkdir -p /opt/corsair/licenses/jacoco \
      /opt/corsair/licenses/jacoco-agent \
      /opt/corsair/licenses/jacoco-cli && \
    curl -fsS -o /opt/corsair/jacoco-agent.jar \
      "https://repo1.maven.org/maven2/org/jacoco/org.jacoco.agent/${JACOCO_VERSION}/org.jacoco.agent-${JACOCO_VERSION}-runtime.jar" && \
    curl -fsS -o /opt/corsair/jacoco-cli.jar \
      "https://repo1.maven.org/maven2/org/jacoco/org.jacoco.cli/${JACOCO_VERSION}/org.jacoco.cli-${JACOCO_VERSION}-nodeps.jar" && \
    curl -fsS -o /opt/corsair/licenses/jacoco/EPL-2.0.txt \
      "https://raw.githubusercontent.com/spdx/license-list-data/v3.27.0/text/EPL-2.0.txt" && \
    echo "3fb76eea65f81bd9415202bab34b6571728841dff1ab8e6bbe81adc2e299face  /opt/corsair/jacoco-agent.jar" | sha256sum -c - && \
    echo "811c7f8c6b358c5d68a8973cfa867f6892be7a671b697a4b13c4b447e6daf75c  /opt/corsair/jacoco-cli.jar" | sha256sum -c - && \
    echo "61616a4066701bc7888ad910de1633dbc55eb4d4d30d930feef55afb9492e33c  /opt/corsair/licenses/jacoco/EPL-2.0.txt" | sha256sum -c - && \
    (cd /opt/corsair/licenses/jacoco-agent && jar xf /opt/corsair/jacoco-agent.jar about.html) && \
    (cd /opt/corsair/licenses/jacoco-cli && jar xf /opt/corsair/jacoco-cli.jar about.html) && \
    test -s /opt/corsair/licenses/jacoco-agent/about.html && \
    test -s /opt/corsair/licenses/jacoco-cli/about.html && \
    java -XshowSettings:properties -version 2>&1 | grep -F "java.runtime.version = 21.0.12.1+1-LTS"
RUN useradd --create-home --uid 1000 corsair
WORKDIR /work
