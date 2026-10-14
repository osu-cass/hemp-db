FROM python:3.14-slim-bookworm AS base

ARG APP_UID=1000
ARG APP_GID=1000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --gid "${APP_GID}" app \
    && useradd --uid "${APP_UID}" --gid app --create-home app
RUN python -m pip install --no-cache-dir --upgrade pip==26.1.2

COPY requirements.txt requirements-dev.txt requirements-production.txt ./


FROM base AS development

RUN pip install --no-cache-dir -r requirements-dev.txt

COPY --chown=app:app . .
COPY --chown=root:root docker/entrypoint.dev.sh /usr/local/bin/hempdb-entrypoint
RUN chmod 755 /usr/local/bin/hempdb-entrypoint

USER app

EXPOSE 8000

ENTRYPOINT ["hempdb-entrypoint"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]


FROM base AS production

RUN pip install --no-cache-dir -r requirements-production.txt

COPY --chown=app:app . .
COPY --chown=root:root docker/entrypoint.sh /usr/local/bin/hempdb-entrypoint
RUN chmod 755 /usr/local/bin/hempdb-entrypoint \
    && mkdir -p /app/staticfiles_build /var/lib/hempdb/auditlogs \
    && chown app:app /app/staticfiles_build /var/lib/hempdb/auditlogs

USER app

RUN SECRET_KEY='container-build-only-secret-key-with-more-than-fifty-unique-characters' \
    ALLOWED_HOSTS='localhost' \
    DATABASE_URL='mysql://unused:unused@localhost/unused' \
    DATABASE_SSL='false' \
    REDIS_URL='redis://localhost:6379/0' \
    python manage.py collectstatic --noinput --clear

EXPOSE 8000

ENTRYPOINT ["hempdb-entrypoint"]
CMD ["gunicorn", "--config", "gunicorn.conf.py", "hempdb.wsgi:application"]
