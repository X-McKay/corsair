# Pilot runtime image for Python probes: pytest for the two native test ids, coverage for the target-line gate.
FROM docker.io/library/python@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704
ENV PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
COPY requirements.lock /opt/corsair/requirements.lock
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --quiet --require-hashes --only-binary=:all: -r /opt/corsair/requirements.lock && \
    test "$(python --version)" = "Python 3.12.15" && \
    python -c "import pytest, coverage; assert pytest.__version__ == '9.0.3'; assert coverage.__version__ == '7.13.4'"
RUN useradd --create-home --uid 1000 corsair
WORKDIR /work
