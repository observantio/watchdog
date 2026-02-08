#!/bin/sh

BACKEND_URL=${BACKEND_URL:-http://beobservant:4319/api/agents/heartbeat}
AGENT_NAME=${AGENT_NAME:-otel-ingester}
AGENT_SYSTEM=${AGENT_SYSTEM:-linux}

while true; do
  HOST=$(hostname)
  PAYLOAD=$(printf '{"id":"%s","name":"%s","system":"%s","metadata":{"host":"%s"}}' "$HOST" "$AGENT_NAME" "$AGENT_SYSTEM" "$HOST")
  curl -s -X POST "$BACKEND_URL" -H "Content-Type: application/json" -d "$PAYLOAD" || true
  sleep 10
done
