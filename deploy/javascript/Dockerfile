# Trusted runtime only.  Target source is bind-mounted read-only at /source.
# Pinned by digest: node:22.23.3-bookworm-slim (linux/amd64). The test runner and V8
# line coverage (node --test, NODE_V8_COVERAGE) are built in; no npm install, no network.
FROM node:22.23.3-bookworm-slim@sha256:3ed98443660ff48413b5af19ecefce3b9d50845a901a43420d47cc63a9fddbe9

# The official node image already defines uid/gid 1000 (user "node"); reuse it.
RUN mkdir -p /opt/corsair /work /tmp \
    && chown -R 1000:1000 /work /tmp \
    && chmod 0555 /opt/corsair

COPY --chmod=0555 src/corsair/adapters/sandboxing/drivers/javascript/driver.mjs /opt/corsair/driver.mjs

# DockerSandbox additionally enforces read_only, no-new-privileges, cap_drop=ALL,
# network_mode=none, PID/CPU/memory limits, and read-only fixture/source/job binds.
USER 1000:1000
WORKDIR /work
ENTRYPOINT ["node", "/opt/corsair/driver.mjs"]
