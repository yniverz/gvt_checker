FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Europe/Berlin \
    GVT_CONFIG=/config/config.yaml \
    GVT_STATE_FILE=/data/state.json

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY gvt_checker ./gvt_checker
COPY config.example.yaml ./config.example.yaml
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod +x /usr/local/bin/entrypoint.sh \
    && useradd --create-home --uid 10001 gvt \
    && mkdir -p /config /data \
    && chown -R gvt:gvt /config /data /app

USER gvt

VOLUME ["/config", "/data"]

HEALTHCHECK --interval=5m --timeout=30s --start-period=30s --retries=3 \
    CMD python -m gvt_checker check-config || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["run"]
