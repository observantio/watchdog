#!/usr/bin/env bash
set -euo pipefail

ENDPOINT="localhost:4318"
DURATION_MINUTES=60
DELAY=0.05
RETRIES=2
INSECURE=true

# Use an array for the insecure flag to avoid word splitting when expanding into the command
if [ "$INSECURE" = true ]; then
  INSECURE_FLAG=(--otlp-insecure)
else
  INSECURE_FLAG=()
fi

TELEMETRYGEN_IMG="ghcr.io/open-telemetry/opentelemetry-collector-contrib/telemetrygen:latest"
DOCKER_RUN="docker run --rm --network host"

SERVICES=(
  "api-gateway"
  "auth-service"
  "payment-service"
  "inventory-service"
  "order-service"
  "notification-service"
)

REGIONS=("us-east-1" "us-west-2" "eu-west-1")
ENVS=("prod" "staging")

LEVELS=("INFO" "INFO" "WARN" "ERROR")

END_TIME=$((SECONDS + DURATION_MINUTES * 60))
COUNT=0

echo "=== Starting continuous log generation for ${DURATION_MINUTES} minutes ==="
echo "Press Ctrl+C to stop"
echo ""

while [ "$SECONDS" -lt "$END_TIME" ]; do
  COUNT=$((COUNT + 1))
  
  ENV="${ENVS[$((RANDOM % ${#ENVS[@]}))]}"
  REGION="${REGIONS[$((RANDOM % ${#REGIONS[@]}))]}"
  SVC="${SERVICES[$((RANDOM % ${#SERVICES[@]}))]}"
  LEVEL="${LEVELS[$((RANDOM % ${#LEVELS[@]}))]}"
  
  LEVEL_EMOJI="ℹ"
  case "$LEVEL" in
    DEBUG) LEVEL_EMOJI="🔍" ;;
    INFO) LEVEL_EMOJI="✓" ;;
    WARN) LEVEL_EMOJI="⚠" ;;
    ERROR) LEVEL_EMOJI="✗" ;;
  esac

  echo "[$COUNT] $LEVEL_EMOJI $LEVEL | $SVC | $ENV/$REGION"

  attempt=0
  CODE=1
  until [[ $attempt -ge $RETRIES ]]; do
    set +e
    $DOCKER_RUN $TELEMETRYGEN_IMG logs \
      --otlp-http \
      --otlp-endpoint "$ENDPOINT" \
      "${INSECURE_FLAG[@]}" \
      --logs 1 \
      --otlp-attributes "service.name=\"$SVC\",env=\"$ENV\",cloud.region=\"$REGION\",log.level=\"$LEVEL\"" \
      >/dev/null 2>&1
    CODE=$?
    set -e

    [[ $CODE -eq 0 ]] && break
    attempt=$((attempt+1))
    sleep 0.5
  done
  
  if [[ $CODE -ne 0 ]]; then
    echo "  FAILED to send logs after $RETRIES attempts"
  fi

  sleep "$DELAY"
  
  if (( COUNT % 50 == 0 )); then
    ELAPSED=$((SECONDS))
    REMAINING=$((END_TIME - SECONDS))
    echo ""
    echo "--- Stats: $COUNT logs sent | ${ELAPSED}s elapsed | ${REMAINING}s remaining ---"
    echo ""
  fi
done

echo ""
echo "=== Complete: $COUNT logs generated over ${DURATION_MINUTES} minutes ==="