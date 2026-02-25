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

# Optional tunables
TRACE_COUNT="${TRACE_COUNT:-1}"
TRACE_PARALLEL="${TRACE_PARALLEL:-1}"
TRACE_LOOPS="${TRACE_LOOPS:-0}"
TRACE_DELAY="${TRACE_DELAY:-0}"

LOG_COUNT="${LOG_COUNT:-1}"
LOG_PARALLEL="${LOG_PARALLEL:-1}"
LOG_LOOPS="${LOG_LOOPS:-0}"
LOG_DELAY="${LOG_DELAY:-0}"

# Delay between launching traces and logs generators
GENERATOR_START_DELAY="${GENERATOR_START_DELAY:-1}"

# traces.py args: <endpoint> <count> <parallel> <loops> <delay>  (loops=0 = infinite)
python3 /app/traces.py 127.0.0.1:4318 "$TRACE_COUNT" "$TRACE_PARALLEL" "$TRACE_LOOPS" "$TRACE_DELAY" &

sleep "$GENERATOR_START_DELAY"

# logs.py args: <endpoint> <count> <parallel> <loops> <delay> (loops=0 = infinite)
python3 /app/logs.py 127.0.0.1:4318 "$LOG_COUNT" "$LOG_PARALLEL" "$LOG_LOOPS" "$LOG_DELAY" &

wait $OTEL_PID
