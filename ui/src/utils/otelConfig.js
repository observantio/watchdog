`
Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
`

import { LOKI_OTLP_ENDPOINT, MIMIR_REMOTE_WRITE, TEMPO_OTLP_ENDPOINT } from './constants'

export function buildOtelYaml(otlpToken, endpoints = {}) {
  const {
    lokiEndpoint = LOKI_OTLP_ENDPOINT,
    tempoEndpoint = TEMPO_OTLP_ENDPOINT,
    mimirEndpoint = MIMIR_REMOTE_WRITE,
  } = endpoints || {}

  return `receivers:
  hostmetrics:
    collection_interval: 1s
    scrapers:
      cpu:
      memory:
      disk:
      filesystem:
      network:
      paging:
      process:
      system:

  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318
      grpc:
        endpoint: 0.0.0.0:4317

processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 512

exporters:
  otlphttp/loki:
    endpoint: "${lokiEndpoint}"
    headers:
      x-otlp-token: "${otlpToken}"
    tls:
      insecure: true
    retry_on_failure:
      enabled: true
      initial_interval: 5s
      max_interval: 30s
      max_elapsed_time: 5m
    sending_queue:
      enabled: true
      num_consumers: 10
      queue_size: 1000

  otlphttp/tempo:
    endpoint: "${tempoEndpoint}"
    headers:
      x-otlp-token: "${otlpToken}"
    tls:
      insecure: true
    retry_on_failure:
      enabled: true
      initial_interval: 5s
      max_interval: 30s
      max_elapsed_time: 5m
    sending_queue:
      enabled: true
      num_consumers: 10
      queue_size: 1000

  prometheusremotewrite/mimir:
    endpoint: "${mimirEndpoint}"
    headers:
      x-otlp-token: "${otlpToken}"
    retry_on_failure:
      enabled: true
      initial_interval: 5s
      max_interval: 30s
      max_elapsed_time: 5m

  debug:
    verbosity: normal

service:
  pipelines:
    logs:
      receivers: [otlp]
      processors: [memory_limiter]
      exporters: [otlphttp/loki, debug]

    traces:
      receivers: [otlp]
      processors: [memory_limiter]
      exporters: [otlphttp/tempo, debug]

    metrics:
      receivers: [hostmetrics, otlp]
      processors: [memory_limiter]
      exporters: [prometheusremotewrite/mimir, debug]

  telemetry:
    logs:
      level: info
`
}
