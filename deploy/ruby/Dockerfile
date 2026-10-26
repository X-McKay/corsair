# Trusted runtime only.  Target source is bind-mounted read-only at /source.
# Ruby 3.1 ships minitest (5.15.0), json, and the built-in Coverage module as default
# gems, so no network install is needed for the secret-disclosure recipe.
FROM ruby:3.1-slim-bookworm@sha256:2704d8eede6d399b07e5475cae41f7e7077edd9e970753f543ddb445f7f0424f

RUN groupadd --gid 1000 corsair \
    && useradd --uid 1000 --gid 1000 --create-home --home-dir /home/corsair --shell /usr/sbin/nologin corsair \
    && mkdir -p /opt/corsair /work /tmp \
    && chown -R 1000:1000 /work /tmp /home/corsair \
    && chmod 0555 /opt/corsair

COPY --chmod=0555 src/corsair/adapters/sandboxing/drivers/ruby/driver.rb /opt/corsair/driver.rb

# DockerSandbox additionally enforces read_only, no-new-privileges, cap_drop=ALL,
# network_mode=none, PID/CPU/memory limits, and read-only fixture/source/job binds.
USER 1000:1000
WORKDIR /work
ENTRYPOINT ["ruby", "/opt/corsair/driver.rb"]
