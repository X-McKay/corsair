# Build from the repository root; source is mounted only at inspection time.
FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704
COPY src/corsair/adapters/sandboxing/inspection_reader.py /opt/corsair/inspection_reader.py
USER 1000:1000
WORKDIR /
CMD ["python", "-I", "-c", "import time; time.sleep(3600)"]
