FROM docker.io/library/maven@sha256:f2cb52730ea0bde9dc8ba20e5e539d000dcdd7ab9e498d70c301fe04fbddb656 AS cache
COPY pom.xml junit-launcher.sha256 /tmp/preparation/
COPY src/ /tmp/preparation/src/
# Trusted preparation: the fixture's test run, the pinned dependency plugin's test classpath (SPEC-0041 discovery)
# and the pinned JUnit Platform console launcher, all through Maven's strict checksums into the offline cache.
# The inventory hashes every cached artifact: all files but checksum sidecars and the resolver's own bookkeeping.
RUN mvn="/usr/share/maven/bin/mvn -B -ntp -C -f /tmp/preparation/pom.xml -Dmaven.repo.local=/opt/corsair-m2" \
    && dependency=org.apache.maven.plugins:maven-dependency-plugin:3.8.1 \
    && $mvn test $dependency:build-classpath -Dmdep.outputFile=target/corsair-test.classpath -Dmdep.includeScope=test \
    && $mvn $dependency:copy -Dartifact=org.junit.platform:junit-platform-console-standalone:1.14.4 -DoutputDirectory=/opt/corsair-junit \
    && sha256sum -c /tmp/preparation/junit-launcher.sha256 \
    && cd /opt/corsair-m2 && find . -type f ! -path './.meta/*' ! -name '*.sha1' ! -name '*.md5' ! -name _remote.repositories \
       ! -name '*.lastUpdated' ! -name resolver-status.properties -print0 \
       | LC_ALL=C sort -z | xargs -0 sha256sum > /opt/corsair-m2.sha256 \
    && mkdir /opt/corsair-fixture && cp -R /tmp/preparation/pom.xml /tmp/preparation/src /opt/corsair-fixture/ \
    && cp /tmp/preparation/junit-launcher.sha256 /opt/corsair-junit.sha256 && rm -rf /tmp/preparation

FROM cache
COPY m2.sha256 /tmp/m2.sha256
# Fail closed (SPEC-0064): the cache must be exactly the reviewed list, file for file and hash for hash, and every
# artifact must have come from Maven Central. Refresh the list with `make maven-hashes` and review its diff.
RUN diff -u /tmp/m2.sha256 /opt/corsair-m2.sha256 \
    && ! find /opt/corsair-m2 -name _remote.repositories -exec cat {} + | grep -v -E -e '^#' -e '>central-8fac3ebd6edbaca3c794783fa38088af0aa128e7=$' \
    && rm /tmp/m2.sha256
ENV HOME=/tmp
USER 10001:10001
