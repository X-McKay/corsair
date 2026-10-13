# Build from repository root: docker build -f deploy/ui/Dockerfile -t <image> .
# Node 22 bookworm-slim and uv 0.12.23 resolved to immutable upstream indexes.
FROM docker.io/library/node@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392 AS frontend
WORKDIR /build/ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY ui/index.html ui/tsconfig.json ui/vite.config.ts ./
COPY ui/src ./src
RUN npm run build

FROM ghcr.io/astral-sh/uv@sha256:61d393e44e249f2e4b526b6c7ddcecce245946826e608e11c93ad4f5bba55b21 AS uv
FROM docker.io/library/python@sha256:2ed6491b93cd49272ee6de2b5a38440c3448360322c089fc23e370722d74179d AS dependencies
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --only-group ui --no-install-project --no-cache --python /usr/local/bin/python3.12

FROM docker.io/library/python@sha256:2ed6491b93cd49272ee6de2b5a38440c3448360322c089fc23e370722d74179d
WORKDIR /app
COPY --from=dependencies /app/.venv /app/.venv
COPY --from=frontend /build/ui/dist /app/ui/dist
COPY src/corsair /app/src/corsair
COPY ui/NOTICE.md /app/ui/NOTICE.md
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CORSAIR_UI_RESULTS=/data/evals \
    CORSAIR_UI_ASSETS=/app/ui/dist \
    CORSAIR_UI_RUNTIME_MATRIX=/config/runtime-matrix.yaml
USER 10001:10001
EXPOSE 8765
CMD ["gunicorn", "--bind", "0.0.0.0:8765", "--workers", "2", "--threads", "4", "--timeout", "30", "--worker-tmp-dir", "/tmp", "--no-control-socket", "--access-logfile", "-", "corsair.web.wsgi:application"]
