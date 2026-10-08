FROM python:3.12-slim

WORKDIR /app

COPY stage-clone/ /app/
RUN cp /app/stage.json /app/stage.seed.json \
    && chmod +x /app/docker-entrypoint.sh

ENV PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    BIND_HOST=0.0.0.0 \
    PORT=8901 \
    HERMES_ENV_FILE=/data/.env

EXPOSE 8901
VOLUME ["/data"]

ENTRYPOINT ["/app/docker-entrypoint.sh"]
