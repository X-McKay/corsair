# Debian-based native C++ probe image. Build replay compiles with --coverage; probes write gcda data only under /tmp.
FROM docker.io/library/debian:bookworm-slim

USER root
ENV DEBIAN_FRONTEND=noninteractive PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 HOME=/tmp
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates cmake curl g++ gcc make ninja-build python3 python3-pip \
    && python3 -m pip install --break-system-packages pytest==9.0.3 coverage==7.13.4 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1000 corsair && useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin corsair \
    && mkdir -p /work && chown 1001:1001 /work && ln -s /usr/bin/python3 /usr/local/bin/python
WORKDIR /work
# Docker builds replay as root. OpenShell SDK builds run as 1001:1001, so /work is pre-owned by that builder; both
# retain a distinct uid-1000 offline probe so sealed source cannot be reopened by a probe.
