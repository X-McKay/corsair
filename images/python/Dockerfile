# Pilot runtime image for Python probes: pytest for the two native test ids, coverage for the target-line gate.
FROM docker.io/library/python@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704
ENV PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --quiet pytest==9.0.3 coverage==7.13.4 && python -c "import pytest, coverage; print(pytest.__version__, coverage.__version__)"
RUN useradd --create-home --uid 1000 corsair
WORKDIR /work
