FROM docker.io/library/node@sha256:c9025a77a42d87e95433337ac581c0d42810c1263f0e78802691046920d1560b
COPY package.json package-lock.json native.test.js /tmp/preparation/
# Trusted preparation: npm ci installs exactly the checked-in lockfile, checking every tarball's SHA-512 integrity,
# into the offline cache; an offline npm ci from that cache and the fixture's Jest run then prove the cache complete.
# Install scripts never run (--ignore-scripts); the upstream image brings Node 8.17.0, npm 6.13.4 and Yarn 1.21.1.
RUN test "$(node --version) $(npm --version) $(yarn --version)" = "v8.17.0 6.13.4 1.21.1" \
    && cd /tmp/preparation && npm="npm --ignore-scripts --no-audit --no-update-notifier --cache /opt/corsair-npm" \
    && $npm ci && rm -rf node_modules && $npm ci --offline \
    && node node_modules/jest/bin/jest.js --ci \
    && mkdir /opt/corsair-fixture && cp package.json package-lock.json native.test.js /opt/corsair-fixture/ \
    && rm -rf /tmp/preparation /opt/corsair-npm/_logs && chmod -R a+rX /opt/corsair-npm /opt/corsair-fixture
ENV HOME=/tmp
USER 10001:10001
