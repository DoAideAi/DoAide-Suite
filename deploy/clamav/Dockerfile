# Official ClamAV 1.4.6 LTS security release, multi-architecture index.
FROM clamav/clamav:1.4.6-debian13-slim@sha256:03a2f641117f0a8c908bac65a63c5e1e4695badc52a340c9d30397d7cebb9154
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3-minimal ca-certificates && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 doaide && useradd --uid 10001 --gid 10001 --no-create-home doaide \
    && mkdir -p /run/clamav /var/lib/clamav && chown -R doaide:doaide /run/clamav /var/lib/clamav
COPY deploy/clamav/clamd.conf deploy/clamav/freshclam.conf /etc/clamav/
COPY deploy/clamav/health.py /health.py
ENV TZ=UTC PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
ENTRYPOINT []
HEALTHCHECK --interval=15s --timeout=5s --start-period=120s CMD ["python3", "/health.py"]
CMD ["clamd", "--foreground=true", "--config-file=/etc/clamav/clamd.conf"]
