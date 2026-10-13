FROM docker.io/library/maven@sha256:5394efaabc436795b507ca400aaf86311db03543072e0e87ae66c595965d4aed
COPY pom.xml junit-launcher.sha256 /tmp/preparation/
COPY src/ /tmp/preparation/src/
# Trusted preparation: the fixture's test run, the pinned dependency plugin's test classpath (SPEC-0041 discovery)
# and the pinned JUnit Platform console launcher, all through Maven's strict checksums into the offline cache.
RUN mvn="/usr/share/maven/bin/mvn -B -ntp -C -f /tmp/preparation/pom.xml -Dmaven.repo.local=/opt/corsair-m2" \
    && dependency=org.apache.maven.plugins:maven-dependency-plugin:3.8.1 \
    && $mvn test $dependency:build-classpath -Dmdep.outputFile=target/corsair-test.classpath -Dmdep.includeScope=test \
    && $mvn $dependency:copy -Dartifact=org.junit.platform:junit-platform-console-standalone:1.14.4 -DoutputDirectory=/opt/corsair-junit \
    && sha256sum -c /tmp/preparation/junit-launcher.sha256 \
    && cd /opt/corsair-m2 && find . -type f \( -name '*.jar' -o -name '*.pom' \) -print0 | sort -z | xargs -0 sha256sum > /opt/corsair-m2.sha256 \
    && mkdir /opt/corsair-fixture && cp -R /tmp/preparation/pom.xml /tmp/preparation/src /opt/corsair-fixture/ \
    && cp /tmp/preparation/junit-launcher.sha256 /opt/corsair-junit.sha256 && rm -rf /tmp/preparation
ENV HOME=/tmp
USER 10001:10001
