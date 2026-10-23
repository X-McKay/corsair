# Pilot runtime image for Python probes: pytest for the two native test ids, coverage for the target-line gate.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
RUN pip install --quiet pytest==9.0.3 coverage==7.13.4 setuptools==80.9.0 wheel==0.45.1 \
    && python -c "import pytest, coverage; print(pytest.__version__, coverage.__version__)"
RUN useradd --create-home --uid 1000 corsair \
    && mkdir -p /work && chown 1001:1001 /work
WORKDIR /work
# Docker replays builds as root and preserves root-owned source. OpenShell instead admits build commands as 1001:1001,
# so the shared work root is owned by that SDK builder; offline probes remain a distinct uid.
