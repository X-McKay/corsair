# Trusted runtime only.  Target C source is bind-mounted read-only at /source; the
# driver compiles it with a fixed harness under AddressSanitizer with gcov coverage.
# The base digest is a supply-chain pin, not the admitted runtime identity: DockerSandbox
# resolves the local image ID and RunManifest records it (see docs/guides/extensions.md).
# gcc 13.3.0 is pinned so the ASan runtime and gcov JSON format match the qualified row.
FROM gcc:13.3.0-bookworm@sha256:1d71f0f3450214bef38fe09e6f610fb6cca90cf97b43f4ce845bfc32a4168818

# Python only orchestrates the trusted compile/run/parse; no target code is Python here.
RUN groupadd --gid 1000 corsair \
    && useradd --uid 1000 --gid 1000 --create-home --home-dir /home/corsair --shell /usr/sbin/nologin corsair \
    && mkdir -p /opt/corsair /work /tmp \
    && chown -R 1000:1000 /work /tmp /home/corsair \
    && chmod 0555 /opt/corsair

COPY --chmod=0555 src/corsair/adapters/sandboxing/drivers/c/driver.py /opt/corsair/driver.py

# DockerSandbox additionally enforces read_only, no-new-privileges, cap_drop=ALL,
# network_mode=none, PID/CPU/memory limits, and read-only fixture/source/job binds.
USER 1000:1000
WORKDIR /work
ENTRYPOINT ["python3", "/opt/corsair/driver.py"]
