# syntax=docker/dockerfile:1
FROM python:3.12-slim as base
RUN pip install poetry==1.8.2
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache
WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN touch README.md
RUN poetry install --no-root && rm -rf $POETRY_CACHE_DIR

FROM python:3.12-slim as loader
RUN apt-get update && apt-get install -y curl
WORKDIR /app
ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"
COPY --from=base ${VIRTUAL_ENV} ${VIRTUAL_ENV}
COPY learning-feeds/loader/loader.py ./
RUN --mount=type=secret,id=linkedin \
    export CLIENT_ID=$(cat /run/secrets/linkedin | cut -d" " -f1) && \
    export CLIENT_SECRET=$(cat /run/secrets/linkedin | cut -d" " -f2) && \
    python loader.py

FROM python:3.12-slim as server
RUN apt-get update && apt-get install -y curl
WORKDIR /app
ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"
COPY --from=base ${VIRTUAL_ENV} ${VIRTUAL_ENV}
COPY --from=loader /app/learning.db ./
COPY learning-feeds/server/server.py learning-feeds/server/log_conf.yml ./
EXPOSE 8080
ENV DB_PATH="learning.db"
CMD [ "uvicorn", "server:app", "--host",  "0.0.0.0", "--port", "8080", "--log-config", "log_conf.yml" ]
