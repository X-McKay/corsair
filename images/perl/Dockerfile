# Perl probe image: the shared Python pytest driver plus native Devel::Cover statement coverage.
FROM docker.io/library/debian:bookworm-slim

USER root
ENV DEBIAN_FRONTEND=noninteractive PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv PATH=/opt/venv/bin:$PATH HOME=/tmp
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates cpanminus make perl python3 python3-venv libdevel-cover-perl \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir pytest==9.0.3 coverage==7.13.4 \
    && /opt/venv/bin/python -c 'import coverage, pytest; print(pytest.__version__, coverage.__version__)' \
    && perl -MDevel::Cover::DB -e 'print "Devel::Cover::DB available\n"' \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1000 corsair && useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin corsair \
    && mkdir -p /work && chown 1001:1001 /work
WORKDIR /work
# Docker build replay deliberately remains root; OpenShell SDK build replay is uid 1001 and therefore receives the
# pre-owned /work root. DockerSandboxes and OpenShell both use a distinct uid-1000 offline probe after sealing.
