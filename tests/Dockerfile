FROM ghcr.io/open-telemetry/opentelemetry-collector-contrib/telemetrygen:v0.145.0 AS telemetrygen

FROM alpine:3.21

RUN apk add --no-cache bash curl openssl tar gzip netcat-openbsd bc python3

RUN curl -L https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v0.145.0/otelcol-contrib_0.145.0_linux_amd64.tar.gz \
    | tar -xz -C /usr/local/bin otelcol-contrib

COPY --from=telemetrygen /telemetrygen /usr/local/bin/telemetrygen

COPY configs/otel-agent.yaml /etc/otel/agent.yaml
COPY traces.py /app/traces.py
COPY logs.py /app/logs.py
COPY start.sh /app/start.sh

WORKDIR /app
RUN chmod +x /app/start.sh
ENTRYPOINT ["/app/start.sh"]