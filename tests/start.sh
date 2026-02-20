#!/usr/bin/env bash
set -euo pipefail

otelcol-contrib --config=/etc/otel/agent.yaml &
OTEL_PID=$!

trap "kill $OTEL_PID 2>/dev/null; exit" SIGINT SIGTERM

echo "Waiting for OTEL Collector..."
until nc -z 127.0.0.1 4317 && nc -z 127.0.0.1 4318; do
  sleep 0.2
done
echo "OTEL Collector ready, starting generators..."

# traces.py args: <endpoint> <count> <parallel> <loops>  (loops=0 = infinite)
python3 /app/traces.py 127.0.0.1:4318 10 12 0 &

# logs.py args: <endpoint> <count> <parallel> <loops> (loops=0 = infinite)
python3 /app/logs.py 127.0.0.1:4318 10 12 0 &

wait $OTEL_PID