# Trusted runtime only. Target source is bind-mounted read-only at /source.
FROM node:24.22.1-bookworm-slim@sha256:55fb5f5a527ea2c5c4a95f963e48ef90aa38c7b346054fdc8ee9957a2b55d205

RUN mkdir -p /opt/corsair /work /tmp \
    && chown -R 1000:1000 /work /tmp /home/node \
    && chmod 0555 /opt/corsair

COPY --chmod=0555 src/corsair/adapters/sandboxing/node/driver.mjs /opt/corsair/driver.mjs
COPY --chmod=0444 src/corsair/adapters/sandboxing/node/probe.test.mjs /opt/corsair/probe.test.mjs

# DockerSandbox additionally enforces read_only, no-new-privileges, cap_drop=ALL,
# network_mode=none, PID/CPU/memory limits, and read-only fixture/source/job binds.
USER 1000:1000
WORKDIR /work
ENTRYPOINT ["node", "/opt/corsair/driver.mjs"]
