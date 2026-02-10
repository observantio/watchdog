#!/usr/bin/env bash
set -euo pipefail

ENDPOINT="localhost:4318"
COUNT=500
DELAY=0.03
RETRIES=2
INSECURE=true

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

TELEMETRYGEN_IMG="ghcr.io/open-telemetry/opentelemetry-collector-contrib/telemetrygen:latest"
DOCKER_RUN="docker run --rm --network host"

FRONTENDS=(
  "web-frontend"
  "mobile-api"
  "admin-portal"
)

GATEWAYS=(
  "api-gateway"
  "graphql-gateway"
)

CORE_SERVICES=(
  "user-service"
  "auth-service"
  "session-service"
  "profile-service"
)

BUSINESS_SERVICES=(
  "order-service"
  "payment-service"
  "inventory-service"
  "shipping-service"
  "pricing-service"
  "catalog-service"
  "cart-service"
  "recommendation-service"
  "search-service"
  "notification-service"
  "email-service"
  "analytics-service"
)

INFRASTRUCTURE=(
  "postgres-primary"
  "postgres-replica"
  "redis-cache"
  "redis-session"
  "kafka-broker"
  "elasticsearch"
  "s3-storage"
  "cdn"
)

EXTERNAL_SERVICES=(
  "stripe-api"
  "sendgrid-api"
  "twilio-api"
  "aws-sqs"
  "datadog-agent"
)

REGIONS=("us-east-1" "us-west-2" "eu-west-1" "ap-southeast-2")
ENVS=("prod" "prod" "prod" "staging")
CUSTOMERS=("customer-a" "customer-b" "customer-c" "premium-corp" "enterprise-co")

hex_id(){
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "$1" 2>/dev/null
  else
    head -c "$1" /dev/urandom | od -An -v -t x1 | tr -d ' \n'
  fi
}

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

send_span(){
  local svc=$1
  local trace=$2
  local parent=$3
  local name=$4
  local dur=$5
  local status=$6
  local attrs=$7

  attrs_with_ids="$attrs,trace_id=\"$trace\""
  if [ -n "$parent" ]; then attrs_with_ids="$attrs_with_ids,parent_span_id=\"$parent\""; fi
  attrs_with_ids="$attrs_with_ids,span.name=\"$name\""

  local status_emoji="✓"
  [[ $status -eq 1 ]] && status_emoji="✗"
  
  echo "  $status_emoji $svc | $name | ${dur}ms"

  attempt=0
  CODE=1
  until [[ $attempt -ge $RETRIES ]]; do
    set +e
    $DOCKER_RUN $TELEMETRYGEN_IMG traces \
      --otlp-http \
      --otlp-endpoint "$ENDPOINT" \
      $( [ "$INSECURE" = true ] && echo --otlp-insecure ) \
      --service "$svc" \
      --traces 1 \
      --span-duration "${dur}ms" \
      --status-code "$status" \
      --telemetry-attributes "$attrs_with_ids" \
      >/dev/null 2>&1
    CODE=$?
    set -e
    [[ $CODE -eq 0 ]] && break
    attempt=$((attempt+1))
    safe_sleep 0.5
  done
  if [[ $CODE -ne 0 ]]; then
    echo "    WARNING: failed after $attempt attempts" >&2
  fi
}

generate_user_flow() {
  local trace_id=$1
  local region=$2
  local env=$3
  local customer=$4
  
  local frontend="${FRONTENDS[$((RANDOM % ${#FRONTENDS[@]}))]}"
  local gateway="${GATEWAYS[$((RANDOM % ${#GATEWAYS[@]}))]}"
  
  local root_span=$(hex_id 8)
  local gw_span=$(hex_id 8)
  
  local route_type=$((RANDOM % 5))
  local route="/api/checkout"
  local method="POST"
  
  case $route_type in
    0) route="/api/products"; method="GET" ;;
    1) route="/api/cart"; method="POST" ;;
    2) route="/api/search"; method="GET" ;;
    3) route="/api/user/profile"; method="GET" ;;
    4) route="/api/checkout"; method="POST" ;;
  esac
  
  local error_rate=$((RANDOM % 100))
  local has_error=0
  [[ $error_rate -lt 3 ]] && has_error=1
  
  echo "[$method $route] $env/$region | customer=$customer | trace=${trace_id:0:8}..."
  
  send_span \
    "$frontend" \
    "$trace_id" \
    "" \
    "$method $route" \
    "$(rand 30 100)" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",http.method=\"$method\",http.route=\"$route\",customer=\"$customer\",tier=\"premium\""
  
  send_span \
    "$gateway" \
    "$trace_id" \
    "$root_span" \
    "$method $route" \
    "$(rand 50 150)" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",http.method=\"$method\",http.route=\"$route\",customer=\"$customer\""
  
  local auth_span=$(hex_id 8)
  send_span \
    "auth-service" \
    "$trace_id" \
    "$gw_span" \
    "ValidateToken" \
    "$(rand 10 40)" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",rpc.method=\"ValidateToken\""
  
  send_span \
    "redis-session" \
    "$trace_id" \
    "$auth_span" \
    "GET session" \
    "$(rand 2 8)" \
    0 \
    "db.system=\"redis\",db.operation=\"GET\""
  
  if [[ "$route" == "/api/products" || "$route" == "/api/search" ]]; then
    generate_product_flow "$trace_id" "$gw_span" "$region" "$env" "$has_error"
  elif [[ "$route" == "/api/cart" ]]; then
    generate_cart_flow "$trace_id" "$gw_span" "$region" "$env" "$has_error"
  elif [[ "$route" == "/api/checkout" ]]; then
    generate_checkout_flow "$trace_id" "$gw_span" "$region" "$env" "$has_error"
  elif [[ "$route" == "/api/user/profile" ]]; then
    generate_profile_flow "$trace_id" "$gw_span" "$region" "$env" "$has_error"
  fi
}

generate_product_flow() {
  local trace_id=$1
  local parent=$2
  local region=$3
  local env=$4
  local has_error=$5
  
  local catalog_span=$(hex_id 8)
  send_span \
    "catalog-service" \
    "$trace_id" \
    "$parent" \
    "GetProducts" \
    "$(rand 40 120)" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",rpc.method=\"GetProducts\""
  
  send_span \
    "postgres-replica" \
    "$trace_id" \
    "$catalog_span" \
    "SELECT products" \
    "$(rand 20 60)" \
    0 \
    "db.system=\"postgresql\",db.operation=\"SELECT\",db.sql.table=\"products\""
  
  send_span \
    "redis-cache" \
    "$trace_id" \
    "$catalog_span" \
    "GET product_cache" \
    "$(rand 2 10)" \
    0 \
    "db.system=\"redis\",db.operation=\"GET\""
  
  local search_span=$(hex_id 8)
  send_span \
    "search-service" \
    "$trace_id" \
    "$parent" \
    "Search" \
    "$(rand 60 200)" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",rpc.method=\"Search\""
  
  send_span \
    "elasticsearch" \
    "$trace_id" \
    "$search_span" \
    "SEARCH products" \
    "$(rand 40 150)" \
    0 \
    "db.system=\"elasticsearch\",db.operation=\"SEARCH\""
  
  local rec_span=$(hex_id 8)
  send_span \
    "recommendation-service" \
    "$trace_id" \
    "$parent" \
    "GetRecommendations" \
    "$(rand 80 250)" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",rpc.method=\"GetRecommendations\""
  
  send_span \
    "redis-cache" \
    "$trace_id" \
    "$rec_span" \
    "GET recommendations" \
    "$(rand 3 12)" \
    0 \
    "db.system=\"redis\",db.operation=\"GET\""
}

generate_cart_flow() {
  local trace_id=$1
  local parent=$2
  local region=$3
  local env=$4
  local has_error=$5
  
  local cart_span=$(hex_id 8)
  send_span \
    "cart-service" \
    "$trace_id" \
    "$parent" \
    "UpdateCart" \
    "$(rand 30 90)" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",rpc.method=\"UpdateCart\""
  
  send_span \
    "redis-cache" \
    "$trace_id" \
    "$cart_span" \
    "SET cart" \
    "$(rand 3 15)" \
    0 \
    "db.system=\"redis\",db.operation=\"SET\""
  
  local inv_span=$(hex_id 8)
  send_span \
    "inventory-service" \
    "$trace_id" \
    "$cart_span" \
    "CheckAvailability" \
    "$(rand 25 70)" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",rpc.method=\"CheckAvailability\""
  
  send_span \
    "postgres-primary" \
    "$trace_id" \
    "$inv_span" \
    "SELECT inventory" \
    "$(rand 15 45)" \
    0 \
    "db.system=\"postgresql\",db.operation=\"SELECT\",db.sql.table=\"inventory\""
  
  local price_span=$(hex_id 8)
  send_span \
    "pricing-service" \
    "$trace_id" \
    "$cart_span" \
    "CalculatePrice" \
    "$(rand 20 60)" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",rpc.method=\"CalculatePrice\""
}

generate_checkout_flow() {
  local trace_id=$1
  local parent=$2
  local region=$3
  local env=$4
  local has_error=$5
  
  local order_span=$(hex_id 8)
  send_span \
    "order-service" \
    "$trace_id" \
    "$parent" \
    "CreateOrder" \
    "$(rand 100 300)" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",rpc.method=\"CreateOrder\""
  
  send_span \
    "postgres-primary" \
    "$trace_id" \
    "$order_span" \
    "INSERT order" \
    "$(rand 30 80)" \
    0 \
    "db.system=\"postgresql\",db.operation=\"INSERT\",db.sql.table=\"orders\""
  
  local payment_span=$(hex_id 8)
  local payment_status=0
  [[ $has_error -eq 1 ]] && payment_status=1
  
  send_span \
    "payment-service" \
    "$trace_id" \
    "$order_span" \
    "ProcessPayment" \
    "$(rand 200 800)" \
    "$payment_status" \
    "env=\"$env\",cloud.region=\"$region\",rpc.method=\"ProcessPayment\""
  
  send_span \
    "stripe-api" \
    "$trace_id" \
    "$payment_span" \
    "POST /v1/charges" \
    "$(rand 150 700)" \
    "$payment_status" \
    "http.method=\"POST\",net.peer.name=\"api.stripe.com\""
  
  if [[ $payment_status -eq 0 ]]; then
    local inv_span=$(hex_id 8)
    send_span \
      "inventory-service" \
      "$trace_id" \
      "$order_span" \
      "ReserveStock" \
      "$(rand 40 100)" \
      0 \
      "env=\"$env\",cloud.region=\"$region\",rpc.method=\"ReserveStock\""
    
    send_span \
      "postgres-primary" \
      "$trace_id" \
      "$inv_span" \
      "UPDATE inventory" \
      "$(rand 25 70)" \
      0 \
      "db.system=\"postgresql\",db.operation=\"UPDATE\",db.sql.table=\"inventory\""
    
    local shipping_span=$(hex_id 8)
    send_span \
      "shipping-service" \
      "$trace_id" \
      "$order_span" \
      "CreateShipment" \
      "$(rand 50 150)" \
      0 \
      "env=\"$env\",cloud.region=\"$region\",rpc.method=\"CreateShipment\""
    
    send_span \
      "postgres-primary" \
      "$trace_id" \
      "$shipping_span" \
      "INSERT shipment" \
      "$(rand 20 60)" \
      0 \
      "db.system=\"postgresql\",db.operation=\"INSERT\",db.sql.table=\"shipments\""
    
    local notif_span=$(hex_id 8)
    send_span \
      "notification-service" \
      "$trace_id" \
      "$order_span" \
      "SendOrderConfirmation" \
      "$(rand 30 90)" \
      0 \
      "env=\"$env\",cloud.region=\"$region\",rpc.method=\"SendOrderConfirmation\""
    
    send_span \
      "email-service" \
      "$trace_id" \
      "$notif_span" \
      "SendEmail" \
      "$(rand 50 200)" \
      0 \
      "env=\"$env\",cloud.region=\"$region\",rpc.method=\"SendEmail\""
    
    send_span \
      "sendgrid-api" \
      "$trace_id" \
      "$notif_span" \
      "POST /v3/mail/send" \
      "$(rand 100 400)" \
      0 \
      "http.method=\"POST\",net.peer.name=\"api.sendgrid.com\""
    
    send_span \
      "kafka-broker" \
      "$trace_id" \
      "$order_span" \
      "PUBLISH order.created" \
      "$(rand 10 40)" \
      0 \
      "messaging.system=\"kafka\",messaging.destination=\"order.created\""
    
    local analytics_span=$(hex_id 8)
    send_span \
      "analytics-service" \
      "$trace_id" \
      "$parent" \
      "TrackEvent" \
      "$(rand 15 50)" \
      0 \
      "env=\"$env\",cloud.region=\"$region\",rpc.method=\"TrackEvent\""
    
    send_span \
      "aws-sqs" \
      "$trace_id" \
      "$analytics_span" \
      "SendMessage" \
      "$(rand 20 80)" \
      0 \
      "messaging.system=\"sqs\""
  fi
}

generate_profile_flow() {
  local trace_id=$1
  local parent=$2
  local region=$3
  local env=$4
  local has_error=$5
  
  local profile_span=$(hex_id 8)
  send_span \
    "profile-service" \
    "$trace_id" \
    "$parent" \
    "GetProfile" \
    "$(rand 30 90)" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",rpc.method=\"GetProfile\""
  
  send_span \
    "postgres-replica" \
    "$trace_id" \
    "$profile_span" \
    "SELECT user_profile" \
    "$(rand 15 50)" \
    0 \
    "db.system=\"postgresql\",db.operation=\"SELECT\",db.sql.table=\"user_profiles\""
  
  send_span \
    "s3-storage" \
    "$trace_id" \
    "$profile_span" \
    "GET avatar" \
    "$(rand 40 120)" \
    0 \
    "aws.service=\"s3\",aws.operation=\"GetObject\""
  
  send_span \
    "cdn" \
    "$trace_id" \
    "$profile_span" \
    "GET static_assets" \
    "$(rand 10 40)" \
    0 \
    "http.url=\"cdn.example.com\""
}

for ((i=1;i<=COUNT;i++)); do
  echo ""
  echo "=== Trace $i/$COUNT ==="
  
  TRACE_ID=$(hex_id 16)
  REGION="${REGIONS[$((RANDOM % ${#REGIONS[@]}))]}"
  ENV="${ENVS[$((RANDOM % ${#ENVS[@]}))]}"
  CUSTOMER="${CUSTOMERS[$((RANDOM % ${#CUSTOMERS[@]}))]}"
  
  generate_user_flow "$TRACE_ID" "$REGION" "$ENV" "$CUSTOMER"
  
  safe_sleep "$DELAY"
done

echo ""
echo "=== Complete: $COUNT traces generated ==="