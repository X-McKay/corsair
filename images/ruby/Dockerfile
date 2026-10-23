# Debian-based Ruby probe image. Ruby target processes load the kernel-owned SimpleCov bootstrap through RUBYOPT.
FROM docker.io/library/ruby:3.2-slim-bookworm

USER root
ENV DEBIAN_FRONTEND=noninteractive PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 HOME=/tmp
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip \
    && ln -sf /usr/bin/python3 /usr/local/bin/python \
    && python -m pip install --break-system-packages pytest==9.0.3 coverage==7.13.4 \
    && gem install --no-document bundler -v 4.0.23 \
    && gem install --no-document rake -v 13.4.2 \
    && gem install --no-document simplecov -v 0.22.0 \
    && rm -rf /var/lib/apt/lists/*

RUN (getent group 1000 >/dev/null || groupadd --gid 1000 corsair) \
    && (getent passwd 1000 >/dev/null || useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin corsair) \
    && mkdir -p /work
WORKDIR /work
# Build replay remains root-owned so a uid-1000 probe cannot change modes on sealed source. DockerSandboxes opens
# every probe explicitly as 1000:1000 after the root-owned tree has been frozen.
USER root
