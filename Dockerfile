# syntax=docker/dockerfile:1
FROM python:3.14-alpine AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app

FROM python:3.14-slim AS build
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends gettext \
    && rm -rf /var/lib/apt/lists/*
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock ./
RUN uv sync --no-cache --locked --no-dev --group build
COPY manage.py ./
COPY config ./config
COPY src ./src
COPY assets ./assets
COPY locale ./locale
# Build-time settings only; production secrets are supplied at runtime.
RUN LICENSE_DEBUG=1 python manage.py tailwind build --force \
    && LICENSE_DEBUG=1 python manage.py compilemessages --ignore .venv \
    && LICENSE_DEBUG=1 python manage.py collectstatic --noinput
RUN rm -rf src/licenses/tests

# Install runtime wheels against musl, independently of the asset builder.
FROM base AS dependencies
COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN UV_PYTHON_DOWNLOADS=never uv sync --no-cache --locked --no-dev

FROM base AS runtime
RUN addgroup -S -g 10001 app \
    && adduser -S -D -H -u 10001 -G app app \
    && mkdir /data && chown app:app /data
COPY --from=dependencies /app/.venv ./.venv
COPY --from=build /app/config ./config
COPY --from=build /app/src ./src
COPY --from=build /app/locale ./locale
COPY --from=build /app/staticfiles ./staticfiles
COPY --from=build /app/manage.py ./manage.py
# Keep the configured static source directory present, without duplicate assets.
RUN mkdir assets
COPY docker/entrypoint.sh docker/gunicorn.conf.py docker/healthcheck.py ./docker/
ENV LICENSE_DATABASE_URL=sqlite:////data/license_store.sqlite3
USER app
EXPOSE 8000
ENTRYPOINT ["sh", "/app/docker/entrypoint.sh"]
CMD ["gunicorn", "--config", "docker/gunicorn.conf.py", "config.wsgi:application"]
