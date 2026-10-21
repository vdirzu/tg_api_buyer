FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_CACHE_DIR=/tmp/uv-cache
WORKDIR /app
RUN --mount=type=secret,id=build_ca_bundle \
    if [ -f /run/secrets/build_ca_bundle ]; then export PIP_CERT=/run/secrets/build_ca_bundle; fi; \
    pip install --no-cache-dir uv==0.12.23
COPY --chown=10001:10001 pyproject.toml uv.lock ./
COPY --chown=10001:10001 app ./app
COPY --chown=10001:10001 migrations ./migrations
COPY --chown=10001:10001 alembic.ini ./
RUN --mount=type=secret,id=build_ca_bundle \
    if [ -f /run/secrets/build_ca_bundle ]; then export SSL_CERT_FILE=/run/secrets/build_ca_bundle; fi; \
    uv sync --frozen --no-dev --no-editable && rm -rf /tmp/uv-cache \
    && groupadd --gid 10001 marketplace && useradd --uid 10001 --gid marketplace --no-create-home marketplace
COPY --chown=10001:10001 data/sample_keys.csv ./data/sample_keys.csv
USER marketplace
CMD [".venv/bin/python", "-m", "app.main"]
