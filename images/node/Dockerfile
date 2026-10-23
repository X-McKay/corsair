# Debian-based Node 22 probe image. Native V8 data is rendered by the pinned c8 toolchain under /opt/corsair/node.
FROM docker.io/library/node:22-bookworm-slim

USER root
ENV DEBIAN_FRONTEND=noninteractive PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 HOME=/tmp \
    PATH=/opt/corsair/node/node_modules/.bin:${PATH}
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip \
    && ln -sf /usr/bin/python3 /usr/local/bin/python \
    && python -m pip install --break-system-packages pytest==9.0.3 coverage==7.13.4 \
    && rm -rf /var/lib/apt/lists/*

# Keep c8, TypeScript, tsx and Vite out of a project-controlled node_modules tree. package-lock.json pins every
# transitive dependency and npm ci verifies its integrity metadata.
COPY package.json package-lock.json /opt/corsair/node/
RUN npm ci --prefix /opt/corsair/node --ignore-scripts --no-audit --no-fund

# The official Node image already provides node:node at 1000:1000. Retain the invariant if the base image changes.
RUN (getent group 1000 >/dev/null || groupadd --gid 1000 corsair) \
    && (getent passwd 1000 >/dev/null || useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin corsair) \
    && mkdir -p /work
WORKDIR /work
# Build replay remains root-owned so a uid-1000 probe cannot change modes on sealed source. DockerSandboxes opens
# every probe explicitly as 1000:1000 after the root-owned tree has been frozen.
USER root
