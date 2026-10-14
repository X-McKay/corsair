FROM docker.io/library/node@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392
COPY package.json package-lock.json native.test.js /tmp/preparation/
# The checked-in lockfile pins every tarball by SHA-512; npm checks the closure online, then offline.
# Install scripts never run. Jest belongs only to this trusted fixture, not a workload's dependencies.
RUN test "$(node --version) $(npm --version) $(yarn --version)" = "v22.23.3 10.9.9 1.22.22" \
    && cd /tmp/preparation && npm="npm --ignore-scripts --no-audit --no-update-notifier --cache /opt/corsair-npm" \
    && $npm ci && rm -rf node_modules && $npm ci --offline \
    && node node_modules/jest/bin/jest.js --ci --runInBand \
    && mkdir /opt/corsair-fixture && cp package.json package-lock.json native.test.js /opt/corsair-fixture/ \
    && rm -rf /tmp/preparation /opt/corsair-npm/_logs && chmod -R a+rX /opt/corsair-npm /opt/corsair-fixture
ENV HOME=/tmp
USER 10001:10001
