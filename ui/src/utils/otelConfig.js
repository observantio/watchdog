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

  const tokenHeader = otlpToken ? `x-otlp-token: "${otlpToken}"` : `# x-otlp-token: <not available>`

  return `
  receivers:
  hostmetrics:
    collection_interval: 30s
    scrapers:
      cpu:
      memory:
      disk:
      filesystem:
      network:
      paging:
      load:
      process:
        mute_process_name_error: true
        mute_process_exe_error: true
        mute_process_io_error: true

  filelog:
    include:
      - /var/log/*.log
      - /var/log/**/*.log
    exclude:
      - /var/log/btmp
      - /var/log/wtmp
    start_at: end
    include_file_path: true
    include_file_name: false
    operators:
      - type: json_parser
        if: 'body matches "^{"'
        parse_from: body
        timestamp:
          parse_from: attributes.time
          layout_type: gotime
          layout: "2006-01-02T15:04:05Z07:00"
      - type: move
        if: 'attributes["log.file.path"] != nil'
        from: attributes["log.file.path"]
        to: resource["log.file.path"]

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
    spike_limit_mib: 128

  resourcedetection:
    detectors: [env, system]
    timeout: 5s
    override: false

  batch:
    send_batch_size: 1000
    send_batch_max_size: 2000
    timeout: 10s

exporters:
  otlp_http/loki:
    endpoint: "${lokiEndpoint}"
    headers:
      ${tokenHeader}
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

  otlp_http/tempo:
    endpoint: "${tempoEndpoint}"
    headers:
      ${tokenHeader}
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
      ${tokenHeader}
    retry_on_failure:
      enabled: true
      initial_interval: 5s
      max_interval: 30s
      max_elapsed_time: 5m

service:
  pipelines:
    logs:
      receivers: [otlp, filelog]
      processors: [memory_limiter, resourcedetection, batch]
      exporters: [otlp_http/loki]

    traces:
      receivers: [otlp]
      processors: [memory_limiter, resourcedetection, batch]
      exporters: [otlp_http/tempo]

    metrics:
      receivers: [hostmetrics, otlp]
      processors: [memory_limiter, resourcedetection, batch]
      exporters: [prometheusremotewrite/mimir]

  telemetry:
    logs:
      level: warn
    metrics:
      level: basic
      readers:
        - pull:
            exporter:
              prometheus:
                host: 0.0.0.0
                port: 8889
`
}