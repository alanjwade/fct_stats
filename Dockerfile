# FCT Stats web application image.
#
# Built and published by .github/workflows/build-push.yml on a `v*` tag.
# This repo's only deployment job is to ship this image; homelab-infra owns
# where/how it runs (see .clinerules/06-deployment-and-cross-workspace.md).

FROM python:3.11-slim

WORKDIR /app

# Python dependencies first (better Docker layer caching).
COPY webapp/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code + config baked into the image.
COPY webapp/ ./
COPY config/ /app/config/

# Persist the build-time version as a runtime env var the app reads.
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

# Runtime paths (match homelab-infra's compose volumes).
ENV DATABASE_PATH=/app/data/db/fct_stats.db
ENV ANALYTICS_DB_PATH=/app/analytics/analytics.db
ENV CONFIG_PATH=/app/config
ENV FLASK_ENV=production

# Writable dirs: /app/data is mounted read-only in production (the db is shipped
# from the dev machine); /app/analytics is writable and holds the analytics db.
RUN mkdir -p /app/data /app/analytics

# Run as a non-root user.
RUN useradd -m -u 1000 webapp && chown -R webapp:webapp /app
USER webapp

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]
