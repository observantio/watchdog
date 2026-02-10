#!/usr/bin/env bash
set -euo pipefail

ENDPOINT="host.docker.internal:4318"
DURATION_MINUTES=60
DELAY=0.05
RETRIES=2
INSECURE=true

if [ "$INSECURE" = true ]; then
  INSECURE_FLAG=(--otlp-insecure)
else
  INSECURE_FLAG=()
fi

TELEMETRYGEN_IMG="ghcr.io/open-telemetry/opentelemetry-collector-contrib/telemetrygen:latest"
DOCKER_RUN="docker run --rm"

SERVICES=(
  "api-gateway"
  "auth-service"
  "payment-service"
  "inventory-service"
  "order-service"
  "notification-service"
  "user-service"
  "analytics-service"
)

REGIONS=("us-east-1" "us-west-2" "eu-west-1" "ap-south-1" "eu-central-1")
ENVS=("prod" "staging" "prod" "prod")

declare -A SERVICE_MESSAGES=(
  [api-gateway]="Request processed successfully|Rate limit applied to client|Circuit breaker opened for downstream service|Request validation failed|Gateway timeout exceeded|Health check passed|SSL handshake completed|WebSocket connection established|Load balancer health degraded|Request queue at capacity"
  [auth-service]="User authentication successful|JWT token issued|Refresh token rotated|Login attempt from new device|Failed login attempt|Password reset requested|MFA challenge sent|Session expired|Invalid credentials|Account locked due to suspicious activity|OAuth callback received|SSO federation completed|API key validated|Token refresh failed|RBAC permission denied"
  [payment-service]="Payment processed successfully|Transaction authorized|Card verification completed|Payment declined by issuer|Fraud detection triggered|Refund initiated|Chargeback received|3DS authentication required|Webhook retry scheduled|Settlement batch completed|Payment method expired|Insufficient funds|High-risk transaction flagged|Currency conversion applied|Payout scheduled"
  [inventory-service]="Stock level updated|Item reserved for order|Low stock alert triggered|SKU replenished|Warehouse sync completed|Dead stock identified|Inventory audit passed|Stock discrepancy detected|Reorder point reached|Backorder created|SKU retired from catalog|Batch expiration warning|Location transfer initiated|Physical count scheduled|Cross-dock shipment received"
  [order-service]="Order created successfully|Order status updated to shipped|Order fulfillment delayed|Payment verification pending|Shipping label generated|Order cancelled by customer|Partial fulfillment processed|Order priority escalated|Delivery confirmation received|Return request initiated|Order split across warehouses|Expedited shipping requested|Address validation failed|Tax calculation completed|Bundle discount applied"
  [notification-service]="Email notification sent|SMS delivery confirmed|Push notification delivered|Webhook POST succeeded|Email bounced|Notification throttled|Template rendering completed|Batch processing started|Unsubscribe request processed|Delivery retry exhausted|Provider rate limit hit|Invalid recipient address|Notification queued for delivery|Channel preference updated|Delivery status callback received"
  [user-service]="User profile updated|Account created successfully|Email verification sent|Profile photo uploaded|Preferences saved|Account deletion requested|Password changed|Two-factor enabled|Session invalidated|User export requested|Privacy settings updated|Subscription upgraded|Profile merge completed|Account suspended|Username availability checked"
  [analytics-service]="Event tracked successfully|Session recorded|Funnel conversion calculated|Real-time dashboard updated|Aggregation job completed|Data pipeline processed batch|A/B test variant assigned|Custom event received|User cohort updated|Report generation started|Cache invalidated|Query optimization applied|Data export scheduled|Sampling rate adjusted|Anomaly detected in metrics"
)

declare -A ERROR_MESSAGES=(
  [api-gateway]="Connection refused to upstream service|Request timeout after 30s|Invalid API key format|CORS preflight failed|Maximum request size exceeded|SSL certificate validation error|Service mesh routing conflict|Upstream returned 503"
  [auth-service]="Database connection pool exhausted|Redis cache unreachable|LDAP server timeout|Token signature verification failed|Session store corrupted|Encryption key rotation failed|OAuth provider unreachable|Certificate expired"
  [payment-service]="Payment gateway timeout|Duplicate transaction detected|PCI compliance violation|Network error during authorization|Merchant account suspended|Invalid card number format|Tokenization service unavailable|Settlement file corruption"
  [inventory-service]="Stock count mismatch critical|Database deadlock detected|Warehouse API unreachable|Concurrent modification conflict|Data replication lag exceeded threshold|SKU not found in catalog|Barcode scanning error|ERP sync failure"
  [order-service]="Shipping carrier API down|Tax calculation service error|Inventory reservation conflict|Database write timeout|Order state machine invalid transition|Address geocoding failed|Payment authorization expired|Fulfillment center unavailable"
  [notification-service]="Email service provider outage|SMS gateway connection lost|Template parsing error|Recipient blacklist lookup failed|Message queue overflow|Delivery webhook timeout|Provider authentication failed|Rate limit quota exceeded"
  [user-service]="Password hash verification timeout|Profile image upload failed|Email uniqueness constraint violated|Account migration error|GDPR export timeout|Session cookie decode error|Avatar service unavailable|Username profanity filter crashed"
  [analytics-service]="ClickHouse connection timeout|Data pipeline stalled|Aggregation query killed|Kafka consumer lag critical|S3 bucket permission denied|Query result too large|Schema evolution failed|Partition pruning error"
)

declare -A WARN_MESSAGES=(
  [api-gateway]="Response time degraded above SLA|Client retry storm detected|Header size approaching limit|Deprecated API version in use|TLS 1.1 connection detected|Upstream latency spike|Cache hit rate below threshold"
  [auth-service]="Password strength below recommended|Multiple failed attempts detected|Token near expiration|Session count above normal|Refresh token reuse detected|Old client version authenticating|Login from unusual location"
  [payment-service]="Transaction amount unusually high|Card nearing expiration|Payment processing slow|Retry attempt for failed payment|Partial authorization received|Currency fluctuation detected|Settlement delayed"
  [inventory-service]="Stock level below threshold|Slow moving inventory identified|Warehouse capacity at 85%|SKU sync latency high|Inventory variance detected|Reorder point approaching|Stock transfer delayed"
  [order-service]="Order processing time elevated|High cancellation rate detected|Shipping zone capacity warning|Address incomplete|Inventory allocation delayed|Order volume spike detected|Fulfillment SLA at risk"
  [notification-service]="Email open rate declining|Delivery latency increasing|Provider failover triggered|Template version deprecated|Bounce rate elevated|Queue depth growing|Retry backoff activated"
  [user-service]="Profile update frequency high|Login session duration unusual|Account age verification needed|Password unchanged for 180 days|Email domain suspicious|Profile completeness low|Export request pending"
  [analytics-service]="Query execution time high|Event processing lag increasing|Storage utilization at 80%|Sampling rate increased|Cache eviction rate high|Dashboard load time elevated|Data freshness delayed"
)

HTTP_CODES=(200 200 200 201 200 204 200 200 400 401 403 404 429 500 502 503)
USERS=("usr_a7f2" "usr_b3k9" "usr_c1m4" "usr_d8n2" "usr_e5p7" "usr_f9q1" "usr_g2r6" "usr_h4s3" "usr_i7t8" "usr_j1u5")
TRACE_IDS=()

generate_trace_id() {
  echo "$(printf '%016x' $RANDOM$RANDOM)$(printf '%016x' $RANDOM$RANDOM)"
}

get_message() {
  local service=$1
  local level=$2
  local messages_var=""
  
  case "$level" in
    ERROR)
      messages_var="ERROR_MESSAGES[$service]"
      ;;
    WARN)
      messages_var="WARN_MESSAGES[$service]"
      ;;
    *)
      messages_var="SERVICE_MESSAGES[$service]"
      ;;
  esac
  
  IFS='|' read -ra MSG_ARRAY <<< "${!messages_var}"
  echo "${MSG_ARRAY[$((RANDOM % ${#MSG_ARRAY[@]}))]}"
}

get_log_level() {
  local rand=$((RANDOM % 100))
  if [ $rand -lt 3 ]; then
    echo "ERROR"
  elif [ $rand -lt 12 ]; then
    echo "WARN"
  elif [ $rand -lt 20 ]; then
    echo "DEBUG"
  else
    echo "INFO"
  fi
}

END_TIME=$((SECONDS + DURATION_MINUTES * 60))
COUNT=0
ERROR_COUNT=0
WARN_COUNT=0

echo "=== Starting continuous log generation for ${DURATION_MINUTES} minutes ==="
echo "Press Ctrl+C to stop"
echo ""

while [ "$SECONDS" -lt "$END_TIME" ]; do
  COUNT=$((COUNT + 1))
  
  ENV="${ENVS[$((RANDOM % ${#ENVS[@]}))]}"
  REGION="${REGIONS[$((RANDOM % ${#REGIONS[@]}))]}"
  SVC="${SERVICES[$((RANDOM % ${#SERVICES[@]}))]}"
  LEVEL=$(get_log_level)
  MESSAGE=$(get_message "$SVC" "$LEVEL")
  HTTP_CODE="${HTTP_CODES[$((RANDOM % ${#HTTP_CODES[@]}))]}"
  USER_ID="${USERS[$((RANDOM % ${#USERS[@]}))]}"
  RESPONSE_TIME=$((RANDOM % 2000 + 50))
  
  if [ ${#TRACE_IDS[@]} -lt 20 ] || [ $((RANDOM % 5)) -eq 0 ]; then
    TRACE_ID=$(generate_trace_id)
    TRACE_IDS+=("$TRACE_ID")
  else
    TRACE_ID="${TRACE_IDS[$((RANDOM % ${#TRACE_IDS[@]}))]}"
  fi
  
  [ "$LEVEL" = "ERROR" ] && ERROR_COUNT=$((ERROR_COUNT + 1))
  [ "$LEVEL" = "WARN" ] && WARN_COUNT=$((WARN_COUNT + 1))
  
  LEVEL_EMOJI="ℹ"
  case "$LEVEL" in
    DEBUG) LEVEL_EMOJI="🔍" ;;
    INFO) LEVEL_EMOJI="✓" ;;
    WARN) LEVEL_EMOJI="⚠" ;;
    ERROR) LEVEL_EMOJI="✗" ;;
  esac

  TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%S.%3NZ")
  echo "[$COUNT] $LEVEL_EMOJI $LEVEL | $SVC | $ENV/$REGION | ${RESPONSE_TIME}ms | $HTTP_CODE | ${MESSAGE:0:60}..."

  STACK_TRACE=""
  if [ "$LEVEL" = "ERROR" ] && [ $((RANDOM % 2)) -eq 0 ]; then
    STACK_TRACE=",error.stack=\"at processRequest (handler.js:234)\nat validateToken (auth.js:89)\at middleware (app.js:45)\""
  fi

  attempt=0
  CODE=1
  until [[ $attempt -ge $RETRIES ]]; do
    set +e
    $DOCKER_RUN $TELEMETRYGEN_IMG logs \
      --otlp-http \
      --otlp-endpoint "$ENDPOINT" \
      "${INSECURE_FLAG[@]}" \
      --logs 1 \
      --body "$MESSAGE" \
      --otlp-attributes "service.name=\"$SVC\",env=\"$ENV\",cloud.region=\"$REGION\",level=\"$LEVEL\",http.status_code=$HTTP_CODE,user.id=\"$USER_ID\",trace.id=\"$TRACE_ID\",response.time_ms=$RESPONSE_TIME,timestamp=\"$TIMESTAMP\"$STACK_TRACE" \
      >/dev/null 2>&1
    CODE=$?
    set -e

    [[ $CODE -eq 0 ]] && break
    attempt=$((attempt+1))
    sleep 0.5
  done
  
  if [[ $CODE -ne 0 ]]; then
    echo "  ⚡ FAILED to send logs after $RETRIES attempts"
  fi

  sleep "$DELAY"
  
  if (( COUNT % 100 == 0 )); then
    ELAPSED=$((SECONDS))
    REMAINING=$((END_TIME - SECONDS))
    ERROR_RATE=$(awk "BEGIN {printf \"%.1f\", ($ERROR_COUNT/$COUNT)*100}")
    WARN_RATE=$(awk "BEGIN {printf \"%.1f\", ($WARN_COUNT/$COUNT)*100}")
    echo ""
    echo "--- Stats: $COUNT logs | ${ELAPSED}s elapsed | ${REMAINING}s remaining | Errors: $ERROR_COUNT ($ERROR_RATE%) | Warnings: $WARN_COUNT ($WARN_RATE%) ---"
    echo ""
  fi
done

echo ""
echo "=== Complete: $COUNT logs generated | Errors: $ERROR_COUNT | Warnings: $WARN_COUNT | Duration: ${DURATION_MINUTES}m ==="