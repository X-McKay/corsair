# Trusted runtime only.  Target source is bind-mounted read-only at /source.
FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704

RUN pip install --no-cache-dir "pytest==9.1.1" "coverage==7.13.0" \
    && groupadd --gid 1000 corsair \
    && useradd --uid 1000 --gid 1000 --create-home --home-dir /home/corsair --shell /usr/sbin/nologin corsair \
    && mkdir -p /opt/corsair /work /tmp \
    && chown -R 1000:1000 /work /tmp /home/corsair \
    && chmod 0555 /opt/corsair

COPY --chmod=0555 src/corsair/tools/security/driver.py /opt/corsair/driver.py

# DockerSandbox additionally enforces read_only, no-new-privileges, cap_drop=ALL,
# network_mode=none, PID/CPU/memory limits, and read-only fixture/source/job binds.
USER 1000:1000
WORKDIR /work
ENTRYPOINT ["python", "/opt/corsair/driver.py"]
