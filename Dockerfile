FROM python:3.12-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b

ARG APP_UID=1000
ARG APP_GID=1000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --gid "${APP_GID}" app \
    && useradd --uid "${APP_UID}" --gid app --create-home app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app . .
COPY --chown=root:root docker/entrypoint.sh /usr/local/bin/hempdb-entrypoint
RUN chmod 755 /usr/local/bin/hempdb-entrypoint

USER app

EXPOSE 8000

ENTRYPOINT ["hempdb-entrypoint"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
