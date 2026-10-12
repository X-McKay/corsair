FROM docker.io/library/maven@sha256:5394efaabc436795b507ca400aaf86311db03543072e0e87ae66c595965d4aed
COPY pom.xml /tmp/preparation/pom.xml
COPY src/ /tmp/preparation/src/
RUN /usr/share/maven/bin/mvn -B -ntp -C -f /tmp/preparation/pom.xml -Dmaven.repo.local=/opt/corsair-m2 test \
    && cd /opt/corsair-m2 && find . -type f \( -name '*.jar' -o -name '*.pom' \) -print0 | sort -z | xargs -0 sha256sum > /opt/corsair-m2.sha256 \
    && mkdir /opt/corsair-fixture && cp -R /tmp/preparation/pom.xml /tmp/preparation/src /opt/corsair-fixture/ && rm -rf /tmp/preparation
ENV HOME=/tmp
USER 10001:10001
