#!/usr/bin/env bash
set -euo pipefail

ENDPOINT="localhost:4318"
DURATION="30s"
RATE=5
MODE="all"
INSECURE=true
TENANT_ID="${TENANT_ID:-default}"

# verify essential dependencies are available
_required=(docker sleep head od tr awk openssl)
_missing=()
for _c in "${_required[@]}"; do
  if ! command -v "$_c" >/dev/null 2>&1; then
    _missing+=("$_c")
  fi
done
if [ "${#_missing[@]}" -gt 0 ]; then
  echo "Missing required commands: ${_missing[*]}. Install them and re-run." >&2
  exit 1
fi

# safe sleep implementation that avoids calling `date` and uses better fallbacks
safe_sleep() {
  local t="$1"
  if command -v sleep >/dev/null 2>&1; then
    sleep "$t"; return
  fi
  if command -v python3 >/dev/null 2>&1; then
    python3 -c "import time; time.sleep($t)"
    return
  fi
  if command -v perl >/dev/null 2>&1; then
    perl -e "select(undef,undef,undef,$t)"
    return
  fi
  local sec=${t%%.*}
  if [ -z "$sec" ]; then sec=0; fi
  local end=$((SECONDS + sec))
  while [ "$SECONDS" -lt "$end" ]; do :; done
}

TG_IMG="ghcr.io/open-telemetry/opentelemetry-collector-contrib/telemetrygen:latest"
DOCKER_RUN="docker run --rm --network host -e OTEL_RESOURCE_ATTRIBUTES=tenant_id=${TENANT_ID}"

SERVICES=("frontend-web" "api-gateway" "auth-service" "order-service" "payment-service" "inventory-service" "notification-worker")

LOG_BODIES=(
  "User login successful"
  "Failed login attempt"
  "Order placed successfully"
  "Payment provider returned 502"
  "Cache miss for product id 1234"
  "Kafka publish succeeded"
  "HTTP 504 timeout upstream service"
)

# portable rand that uses shuf if available, otherwise Python fallback
rand() {
  local min=$1; local max=$2
  if command -v shuf >/dev/null 2>&1; then
    shuf -i "${min}-${max}" -n1
  else
    local range=$((max - min + 1))
    local r=$(( (RANDOM << 15 | RANDOM) % range + min ))
    echo "$r"
  fi
}
hex(){
  local n="$1"
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "$n" 2>/dev/null
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    python3 - <<PY
import secrets,sys
n=int(sys.argv[1])
print(secrets.token_hex(n))
PY
    return
  fi
  local out=""
  for ((i=0;i<n;i++)); do
    out+=$(printf "%02x" $((RANDOM % 256)))
  done
  printf "%s" "$out"
}

# proper array random picker
random_pick() { local arr=("$@"); echo "${arr[RANDOM % ${#arr[@]}]}"; }

# duration parsing
duration_seconds=0
if [[ "$DURATION" =~ ^([0-9]+)(s|m|h)$ ]]; then
    value=${BASH_REMATCH[1]}
    unit=${BASH_REMATCH[2]}
    case "$unit" in
        s) duration_seconds=$value ;;
        m) duration_seconds=$((value*60)) ;;
        h) duration_seconds=$((value*3600)) ;;
    esac
else
    echo "Invalid duration format: $DURATION (use 10s, 5m, 1h)"
    exit 1
fi

END=$(( $(date +%s) + duration_seconds ))
echo "Super fuzzy telemetry launcher → $MODE mode for $DURATION"

while [[ $(date +%s) -lt $END ]]; do
  TRACE_ID=$(hex 16)
  SPAN_ID=$(hex 8)
  CHILD_SPANS=$(rand 1 3)
  SVC=$(random_pick "${SERVICES[@]}")

  if [[ "$MODE" == "traces" || "$MODE" == "all" ]]; then
  $DOCKER_RUN $TG_IMG traces \
  --otlp-http --otlp-endpoint "$ENDPOINT" $( [ "$INSECURE" = true ] && echo --otlp-insecure ) \
  --service "$SVC" --traces 1 --child-spans "$CHILD_SPANS" \
  --telemetry-attributes "trace_id=\"$TRACE_ID\"" \
  --span-duration "$(rand 50 400)ms" --duration "$(rand 200 1000)ms" \
  --rate "$RATE"
  fi

  if [[ "$MODE" == "logs" || "$MODE" == "all" ]]; then
    BODY=$(random_pick "${LOG_BODIES[@]}")
    $DOCKER_RUN $TG_IMG logs \
      --otlp-http --otlp-endpoint "$ENDPOINT" $( [ "$INSECURE" = true ] && echo --otlp-insecure ) \
      --service "$SVC" --logs 1 --body "$BODY" \
      --telemetry-attributes "trace_id=\"$TRACE_ID\",span_id=\"$SPAN_ID\"" \
      --rate "$RATE"
  fi

  if [[ "$MODE" == "dependencies" || "$MODE" == "all" ]]; then
    DEP_SVC=$SVC
    for _ in {1..5}; do
      DEP_SVC=$(random_pick "${SERVICES[@]}")
      [[ "$DEP_SVC" != "$SVC" ]] && break
    done
    STATUS=0
    (( RANDOM % 10 == 0 )) && STATUS=1
    $DOCKER_RUN $TG_IMG traces \
    --otlp-http --otlp-endpoint "$ENDPOINT" $( [ "$INSECURE" = true ] && echo --otlp-insecure ) \
    --service "$DEP_SVC" --traces 1 --child-spans 1 \
    --telemetry-attributes "trace_id=\"$TRACE_ID\",parent_span_id=\"$SPAN_ID\",span.name=\"RPC call to $DEP_SVC\"" \
    --span-duration "$(rand 50 300)ms" --status-code "$( [ $STATUS -eq 0 ] && echo Ok || echo Error )" \
    --rate "$RATE"
  fi

  safe_sleep $(awk -v min=0.01 -v max=0.2 'BEGIN{srand(); print min+rand()*(max-min)}')
done

echo "Super fuzzy telemetry run complete. Check Grafana/Loki/Tempo for realistic traffic."