# Trusted runtime only.  Target source is bind-mounted read-only at /source.
# Pinned by digest as a supply-chain pin; DockerSandbox resolves the tag to an immutable
# local image ID for each run (that ID, not this digest, is the admitted runtime identity).
FROM perl:5.40-slim@sha256:16c8aa12d492a36e13a3467326230e1651480e7e574165490d74f7c092b19e09

# Test::More and JSON::PP are core modules; line coverage is a fixed core-only tracer the
# driver writes at run time (Devel::LineCover via `perl -d:`), so there is no CPAN install
# and no network at run time.
RUN groupadd --gid 1000 corsair \
    && useradd --uid 1000 --gid 1000 --create-home --home-dir /home/corsair --shell /usr/sbin/nologin corsair \
    && mkdir -p /opt/corsair /work /tmp \
    && chown -R 1000:1000 /work /tmp /home/corsair \
    && chmod 0555 /opt/corsair

COPY --chmod=0555 src/corsair/adapters/sandboxing/drivers/perl/driver.pl /opt/corsair/driver.pl

# DockerSandbox additionally enforces read_only, no-new-privileges, cap_drop=ALL,
# network_mode=none, PID/CPU/memory limits, and read-only fixture/source/job binds.
USER 1000:1000
WORKDIR /work
ENTRYPOINT ["perl", "/opt/corsair/driver.pl"]
