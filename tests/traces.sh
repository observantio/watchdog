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
  "web-ui"
  "mobile-ios-app"
  "mobile-android-app"
  "desktop-electron"
  "admin-dashboard"
)

GATEWAYS=(
  "edge-gateway"
  "graphql-api"
  "rest-api-v2"
)

CORE_SERVICES=(
  "identity-provider"
  "auth-svc"
  "session-manager"
  "user-profile-api"
  "permissions-engine"
)

BUSINESS_SERVICES=(
  "orders-api"
  "payments-processor"
  "inventory-mgmt"
  "fulfillment-svc"
  "pricing-engine"
  "product-catalog"
  "shopping-cart-api"
  "ml-recommendations"
  "search-indexer"
  "notifications-hub"
  "email-dispatcher"
  "event-tracker"
  "fraud-detection"
  "tax-calculator"
  "promo-engine"
)

INFRASTRUCTURE=(
  "postgres-master"
  "postgres-read-replica-1"
  "postgres-read-replica-2"
  "redis-primary"
  "redis-replica"
  "kafka-cluster"
  "elasticsearch-node"
  "mongodb-shard-1"
  "s3-object-store"
  "cloudfront-cdn"
  "memcached-cluster"
)

EXTERNAL_SERVICES=(
  "stripe-payments-api"
  "sendgrid-smtp"
  "twilio-messaging"
  "aws-sqs-queue"
  "datadog-metrics"
  "shipstation-api"
  "taxjar-api"
  "auth0-identity"
)

REGIONS=("us-east-1" "us-west-2" "eu-west-1" "ap-southeast-1" "ap-northeast-1")
ENVS=("production" "production" "production" "staging" "canary")
CUSTOMERS=("acme-corp" "globex-inc" "initech-ltd" "hooli-xyz" "umbrella-corp" "massive-dynamic" "cyberdyne")
USER_TIERS=("free" "premium" "enterprise" "trial")

GLOBAL_STATE_DEGRADED_SERVICES=()
GLOBAL_STATE_CIRCUIT_OPEN=()
GLOBAL_STATE_HIGH_LATENCY_REGIONS=()
TRACE_COUNT=0
ERROR_COUNT=0
TIMEOUT_COUNT=0
CIRCUIT_BREAKER_COUNT=0

hex_id(){
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "$1" 2>/dev/null
  else
    head -c "$1" /dev/urandom | od -An -v -t x1 | tr -d ' \n'
  fi
}

rand() {
  local min=$1
  local max=$2
  if command -v shuf >/dev/null 2>&1; then
    shuf -i "${min}-${max}" -n1
  else
    local range=$((max - min + 1))
    local r=$(( (RANDOM << 15 | RANDOM) % range + min ))
    echo "$r"
  fi
}

is_service_degraded() {
  local svc=$1
  for degraded in "${GLOBAL_STATE_DEGRADED_SERVICES[@]}"; do
    [[ "$degraded" == "$svc" ]] && return 0
  done
  return 1
}

is_circuit_open() {
  local svc=$1
  for circuit in "${GLOBAL_STATE_CIRCUIT_OPEN[@]}"; do
    [[ "$circuit" == "$svc" ]] && return 0
  done
  return 1
}

is_region_slow() {
  local region=$1
  for slow_region in "${GLOBAL_STATE_HIGH_LATENCY_REGIONS[@]}"; do
    [[ "$slow_region" == "$region" ]] && return 0
  done
  return 1
}

update_global_state() {
  local trigger=$((RANDOM % 100))
  
  if [ $trigger -lt 2 ] && [ ${#GLOBAL_STATE_DEGRADED_SERVICES[@]} -lt 3 ]; then
    local svc="${BUSINESS_SERVICES[$((RANDOM % ${#BUSINESS_SERVICES[@]}))]}"
    GLOBAL_STATE_DEGRADED_SERVICES+=("$svc")
    echo ""
    echo "🔥 INCIDENT: $svc is experiencing degraded performance"
    echo ""
  fi
  
  if [ $trigger -ge 98 ] && [ ${#GLOBAL_STATE_DEGRADED_SERVICES[@]} -gt 0 ]; then
    local idx=$((RANDOM % ${#GLOBAL_STATE_DEGRADED_SERVICES[@]}))
    local recovered="${GLOBAL_STATE_DEGRADED_SERVICES[$idx]}"
    unset 'GLOBAL_STATE_DEGRADED_SERVICES[$idx]'
    GLOBAL_STATE_DEGRADED_SERVICES=("${GLOBAL_STATE_DEGRADED_SERVICES[@]}")
    echo ""
    echo "✅ RECOVERED: $recovered is back to normal"
    echo ""
  fi
  
  if [ $trigger -eq 5 ] && [ ${#GLOBAL_STATE_CIRCUIT_OPEN[@]} -lt 2 ]; then
    local svc="${EXTERNAL_SERVICES[$((RANDOM % ${#EXTERNAL_SERVICES[@]}))]}"
    GLOBAL_STATE_CIRCUIT_OPEN+=("$svc")
    echo ""
    echo "⚡ CIRCUIT BREAKER: $svc circuit opened due to errors"
    echo ""
  fi
  
  if [ $trigger -eq 95 ] && [ ${#GLOBAL_STATE_CIRCUIT_OPEN[@]} -gt 0 ]; then
    local idx=$((RANDOM % ${#GLOBAL_STATE_CIRCUIT_OPEN[@]}))
    local closed="${GLOBAL_STATE_CIRCUIT_OPEN[$idx]}"
    unset 'GLOBAL_STATE_CIRCUIT_OPEN[$idx]'
    GLOBAL_STATE_CIRCUIT_OPEN=("${GLOBAL_STATE_CIRCUIT_OPEN[@]}")
    echo ""
    echo "🔓 CIRCUIT CLOSED: $closed circuit breaker reset"
    echo ""
  fi
  
  if [ $trigger -eq 10 ] && [ ${#GLOBAL_STATE_HIGH_LATENCY_REGIONS[@]} -lt 2 ]; then
    local region="${REGIONS[$((RANDOM % ${#REGIONS[@]}))]}"
    GLOBAL_STATE_HIGH_LATENCY_REGIONS+=("$region")
    echo ""
    echo "🌐 NETWORK ISSUE: High latency detected in $region"
    echo ""
  fi
  
  if [ $trigger -eq 90 ] && [ ${#GLOBAL_STATE_HIGH_LATENCY_REGIONS[@]} -gt 0 ]; then
    local idx=$((RANDOM % ${#GLOBAL_STATE_HIGH_LATENCY_REGIONS[@]}))
    local recovered="${GLOBAL_STATE_HIGH_LATENCY_REGIONS[$idx]}"
    unset 'GLOBAL_STATE_HIGH_LATENCY_REGIONS[$idx]'
    GLOBAL_STATE_HIGH_LATENCY_REGIONS=("${GLOBAL_STATE_HIGH_LATENCY_REGIONS[@]}")
    echo ""
    echo "📡 NETWORK RESTORED: $recovered latency back to normal"
    echo ""
  fi
}

get_latency_multiplier() {
  local service=$1
  local region=$2
  local base_multiplier=1.0
  
  is_service_degraded "$service" && base_multiplier=3.5
  is_region_slow "$region" && base_multiplier=$(awk "BEGIN {print $base_multiplier * 2.2}")
  
  local random_spike=$((RANDOM % 100))
  [ $random_spike -lt 3 ] && base_multiplier=$(awk "BEGIN {print $base_multiplier * 4.0}")
  
  echo "$base_multiplier"
}

apply_latency() {
  local base=$1
  local multiplier=$2
  awk "BEGIN {printf \"%.0f\", $base * $multiplier}"
}

send_span(){
  local svc=$1
  local trace=$2
  local parent=$3
  local name=$4
  local dur=$5
  local status=$6
  local attrs=$7
  local http_code=${8:-200}
  local error_msg=${9:-""}

  attrs_with_ids="$attrs,trace_id=\"$trace\""
  if [ -n "$parent" ]; then
    attrs_with_ids="$attrs_with_ids,parent_span_id=\"$parent\""
  fi
  attrs_with_ids="$attrs_with_ids,span.name=\"$name\",http.status_code=$http_code"
  
  if [ -n "$error_msg" ]; then
    attrs_with_ids="$attrs_with_ids,error.message=\"$error_msg\",error.type=\"ServiceException\""
  fi

  local status_emoji="✓"
  local status_color=""
  case "$status" in
    0) status_emoji="✓"; status_color="" ;;
    1) status_emoji="✗"; status_color=""; ERROR_COUNT=$((ERROR_COUNT + 1)) ;;
    2) status_emoji="⏱"; status_color=""; TIMEOUT_COUNT=$((TIMEOUT_COUNT + 1)) ;;
  esac
  
  local display_dur="${dur}ms"
  if [ "$dur" -gt 1000 ]; then
    display_dur="${dur}ms ⚠️"
  elif [ "$dur" -gt 3000 ]; then
    display_dur="${dur}ms 🐌"
  fi
  
  local display_code=""
  if [ "$http_code" != "200" ]; then
    display_code=" [$http_code]"
  fi
  
  printf "    %s %-25s | %-35s | %8s%s\n" "$status_emoji" "$svc" "$name" "$display_dur" "$display_code"
  
  if [ -n "$error_msg" ]; then
    echo "       ↳ Error: $error_msg"
  fi

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
    echo "       ⚡ Telemetry send failed after $RETRIES attempts" >&2
  fi
}

generate_user_journey() {
  local trace_id=$1
  local region=$2
  local env=$3
  local customer=$4
  local user_tier=$5
  
  TRACE_COUNT=$((TRACE_COUNT + 1))
  
  local frontend="${FRONTENDS[$((RANDOM % ${#FRONTENDS[@]}))]}"
  local gateway="${GATEWAYS[$((RANDOM % ${#GATEWAYS[@]}))]}"
  
  local root_span=$(hex_id 8)
  local gw_span=$(hex_id 8)
  
  local journey_type=$((RANDOM % 10))
  local route="/api/checkout"
  local method="POST"
  local journey_name="Checkout Flow"
  
  case $journey_type in
    0|1) route="/api/products/search"; method="GET"; journey_name="Product Search" ;;
    2) route="/api/products/{id}"; method="GET"; journey_name="Product Detail" ;;
    3) route="/api/cart/items"; method="POST"; journey_name="Add to Cart" ;;
    4) route="/api/cart/items"; method="DELETE"; journey_name="Remove from Cart" ;;
    5) route="/api/user/profile"; method="GET"; journey_name="View Profile" ;;
    6) route="/api/user/preferences"; method="PUT"; journey_name="Update Preferences" ;;
    7) route="/api/orders/history"; method="GET"; journey_name="Order History" ;;
    8) route="/api/checkout"; method="POST"; journey_name="Complete Checkout" ;;
    9) route="/api/recommendations"; method="GET"; journey_name="Get Recommendations" ;;
  esac
  
  local base_error_rate=2
  is_region_slow "$region" && base_error_rate=8
  [ "$env" == "canary" ] && base_error_rate=12
  
  local error_check=$((RANDOM % 100))
  local has_journey_error=0
  [[ $error_check -lt $base_error_rate ]] && has_journey_error=1
  
  local user_id="user_$(hex_id 6)"
  local session_id="sess_$(hex_id 8)"
  
  echo ""
  echo "═══ Trace $TRACE_COUNT/$COUNT: $journey_name ═══"
  echo "    Route: $method $route"
  echo "    Customer: $customer | Tier: $user_tier | Region: $region | Env: $env"
  echo "    TraceID: ${trace_id:0:16}..."
  
  local latency_mult=$(get_latency_multiplier "$frontend" "$region")
  local frontend_dur=$(apply_latency $(rand 40 120) "$latency_mult")
  
  send_span \
    "$frontend" \
    "$trace_id" \
    "" \
    "HTTP $method $route" \
    "$frontend_dur" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",http.method=\"$method\",http.route=\"$route\",customer=\"$customer\",user.tier=\"$user_tier\",user.id=\"$user_id\",session.id=\"$session_id\"" \
    200
  
  latency_mult=$(get_latency_multiplier "$gateway" "$region")
  local gw_dur=$(apply_latency $(rand 30 100) "$latency_mult")
  
  send_span \
    "$gateway" \
    "$trace_id" \
    "$root_span" \
    "route:$method:$route" \
    "$gw_dur" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",http.method=\"$method\",http.route=\"$route\",customer=\"$customer\",gateway.version=\"v2.4.1\"" \
    200
  
  local auth_result=$(generate_auth_flow "$trace_id" "$gw_span" "$region" "$env" "$user_id" "$session_id")
  local auth_failed=$(echo "$auth_result" | cut -d: -f1)
  
  if [ "$auth_failed" == "1" ]; then
    echo "    ⛔ Authentication failed - aborting request"
    return
  fi
  
  if [[ "$route" == *"/products"* || "$route" == *"/search"* ]]; then
    generate_product_search_flow "$trace_id" "$gw_span" "$region" "$env" "$has_journey_error" "$user_id"
  elif [[ "$route" == *"/cart"* ]]; then
    generate_cart_management_flow "$trace_id" "$gw_span" "$region" "$env" "$has_journey_error" "$method" "$user_id"
  elif [[ "$route" == *"/checkout"* ]]; then
    generate_checkout_transaction_flow "$trace_id" "$gw_span" "$region" "$env" "$has_journey_error" "$user_tier" "$user_id"
  elif [[ "$route" == *"/profile"* || "$route" == *"/preferences"* ]]; then
    generate_user_data_flow "$trace_id" "$gw_span" "$region" "$env" "$has_journey_error" "$method" "$user_id"
  elif [[ "$route" == *"/orders"* ]]; then
    generate_order_history_flow "$trace_id" "$gw_span" "$region" "$env" "$has_journey_error" "$user_id"
  elif [[ "$route" == *"/recommendations"* ]]; then
    generate_ml_recommendations_flow "$trace_id" "$gw_span" "$region" "$env" "$has_journey_error" "$user_id"
  fi
}

generate_auth_flow() {
  local trace_id=$1
  local parent=$2
  local region=$3
  local env=$4
  local user_id=$5
  local session_id=$6
  
  local auth_span=$(hex_id 8)
  local latency_mult=$(get_latency_multiplier "auth-svc" "$region")
  
  local cache_hit=$((RANDOM % 100))
  local auth_duration
  local auth_status=0
  local auth_failed=0
  
  if [ $cache_hit -lt 70 ]; then
    auth_duration=$(apply_latency $(rand 8 25) "$latency_mult")
    send_span \
      "auth-svc" \
      "$trace_id" \
      "$parent" \
      "jwt.validate" \
      "$auth_duration" \
      0 \
      "env=\"$env\",cloud.region=\"$region\",auth.cache_hit=true,user.id=\"$user_id\"" \
      200
    
    local redis_dur=$(apply_latency $(rand 2 6) 1.0)
    send_span \
      "redis-primary" \
      "$trace_id" \
      "$auth_span" \
      "GET auth:token:$session_id" \
      "$redis_dur" \
      0 \
      "db.system=\"redis\",db.operation=\"GET\",cache.hit=true" \
      200
  else
    local auth_failure=$((RANDOM % 100))
    if [ $auth_failure -lt 5 ]; then
      auth_duration=$(apply_latency $(rand 45 120) "$latency_mult")
      auth_status=1
      auth_failed=1
      send_span \
        "auth-svc" \
        "$trace_id" \
        "$parent" \
        "jwt.validate" \
        "$auth_duration" \
        1 \
        "env=\"$env\",cloud.region=\"$region\",auth.cache_hit=false,user.id=\"$user_id\"" \
        401 \
        "Invalid or expired token"
    else
      auth_duration=$(apply_latency $(rand 35 80) "$latency_mult")
      send_span \
        "auth-svc" \
        "$trace_id" \
        "$parent" \
        "jwt.validate" \
        "$auth_duration" \
        0 \
        "env=\"$env\",cloud.region=\"$region\",auth.cache_hit=false,user.id=\"$user_id\"" \
        200
      
      local identity_span=$(hex_id 8)
      local identity_dur=$(apply_latency $(rand 25 60) "$latency_mult")
      send_span \
        "identity-provider" \
        "$trace_id" \
        "$auth_span" \
        "verifyCredentials" \
        "$identity_dur" \
        0 \
        "env=\"$env\",cloud.region=\"$region\",user.id=\"$user_id\"" \
        200
      
      local db_dur=$(apply_latency $(rand 15 40) 1.0)
      send_span \
        "postgres-read-replica-1" \
        "$trace_id" \
        "$identity_span" \
        "SELECT FROM users WHERE id=$user_id" \
        "$db_dur" \
        0 \
        "db.system=\"postgresql\",db.operation=\"SELECT\",db.table=\"users\"" \
        200
    fi
  fi
  
  echo "$auth_failed:$auth_span"
}

generate_product_search_flow() {
  local trace_id=$1
  local parent=$2
  local region=$3
  local env=$4
  local has_error=$5
  local user_id=$6
  
  local catalog_span=$(hex_id 8)
  local latency_mult=$(get_latency_multiplier "product-catalog" "$region")
  local catalog_dur=$(apply_latency $(rand 45 130) "$latency_mult")
  
  send_span \
    "product-catalog" \
    "$trace_id" \
    "$parent" \
    "fetchProductList" \
    "$catalog_dur" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",product.category=\"electronics\"" \
    200
  
  local cache_miss=$((RANDOM % 100))
  if [ $cache_miss -lt 25 ]; then
    local db_dur=$(apply_latency $(rand 80 250) 1.5)
    send_span \
      "postgres-read-replica-2" \
      "$trace_id" \
      "$catalog_span" \
      "SELECT * FROM products WHERE category=?" \
      "$db_dur" \
      0 \
      "db.system=\"postgresql\",db.operation=\"SELECT\",db.table=\"products\",cache.miss=true,query.slow=true" \
      200
    
    echo "       ⚠️  Cache miss caused slow database query"
  else
    local redis_dur=$(apply_latency $(rand 3 12) 1.0)
    send_span \
      "redis-primary" \
      "$trace_id" \
      "$catalog_span" \
      "GET products:catalog:electronics" \
      "$redis_dur" \
      0 \
      "db.system=\"redis\",db.operation=\"GET\",cache.hit=true" \
      200
  fi
  
  local search_span=$(hex_id 8)
  latency_mult=$(get_latency_multiplier "search-indexer" "$region")
  local search_dur=$(apply_latency $(rand 70 220) "$latency_mult")
  
  local search_timeout=$((RANDOM % 100))
  if [ $search_timeout -lt 4 ]; then
    send_span \
      "search-indexer" \
      "$trace_id" \
      "$parent" \
      "executeSearch" \
      "5000" \
      2 \
      "env=\"$env\",cloud.region=\"$region\",search.query=\"laptop\"" \
      504 \
      "Search timeout after 5000ms"
  else
    send_span \
      "search-indexer" \
      "$trace_id" \
      "$parent" \
      "executeSearch" \
      "$search_dur" \
      0 \
      "env=\"$env\",cloud.region=\"$region\",search.query=\"laptop\",search.results=127" \
      200
    
    local es_dur=$(apply_latency $(rand 50 180) 1.0)
    local es_status=0
    local es_code=200
    
    local es_overload=$((RANDOM % 100))
    if [ $es_overload -lt 3 ]; then
      es_dur=3500
      es_status=1
      es_code=429
      send_span \
        "elasticsearch-node" \
        "$trace_id" \
        "$search_span" \
        "SEARCH products index" \
        "$es_dur" \
        "$es_status" \
        "db.system=\"elasticsearch\",db.operation=\"SEARCH\",index=\"products\"" \
        "$es_code" \
        "Circuit breaker tripped: too many requests"
    else
      send_span \
        "elasticsearch-node" \
        "$trace_id" \
        "$search_span" \
        "SEARCH products index" \
        "$es_dur" \
        0 \
        "db.system=\"elasticsearch\",db.operation=\"SEARCH\",index=\"products\"" \
        200
    fi
  fi
  
  local rec_span=$(hex_id 8)
  generate_ml_recommendations_flow "$trace_id" "$parent" "$region" "$env" 0 "$user_id"
}

generate_cart_management_flow() {
  local trace_id=$1
  local parent=$2
  local region=$3
  local env=$4
  local has_error=$5
  local method=$6
  local user_id=$7
  
  local cart_span=$(hex_id 8)
  local latency_mult=$(get_latency_multiplier "shopping-cart-api" "$region")
  local cart_dur=$(apply_latency $(rand 35 95) "$latency_mult")
  
  local operation="addItem"
  [ "$method" == "DELETE" ] && operation="removeItem"
  
  send_span \
    "shopping-cart-api" \
    "$trace_id" \
    "$parent" \
    "cart.$operation" \
    "$cart_dur" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",user.id=\"$user_id\",cart.item_count=3" \
    200
  
  local redis_op="SETEX"
  [ "$method" == "DELETE" ] && redis_op="DEL"
  local redis_dur=$(apply_latency $(rand 4 18) 1.0)
  
  local redis_failure=$((RANDOM % 100))
  if [ $redis_failure -lt 2 ]; then
    send_span \
      "redis-primary" \
      "$trace_id" \
      "$cart_span" \
      "$redis_op cart:$user_id" \
      "1200" \
      1 \
      "db.system=\"redis\",db.operation=\"$redis_op\"" \
      503 \
      "Connection pool exhausted"
  else
    send_span \
      "redis-primary" \
      "$trace_id" \
      "$cart_span" \
      "$redis_op cart:$user_id" \
      "$redis_dur" \
      0 \
      "db.system=\"redis\",db.operation=\"$redis_op\"" \
      200
  fi
  
  if [ "$method" == "POST" ]; then
    local inv_span=$(hex_id 8)
    latency_mult=$(get_latency_multiplier "inventory-mgmt" "$region")
    local inv_dur=$(apply_latency $(rand 30 85) "$latency_mult")
    
    send_span \
      "inventory-mgmt" \
      "$trace_id" \
      "$cart_span" \
      "stock.checkAvailability" \
      "$inv_dur" \
      0 \
      "env=\"$env\",cloud.region=\"$region\",sku=\"LAPTOP-001\"" \
      200
    
    local inv_db_dur=$(apply_latency $(rand 18 55) 1.0)
    send_span \
      "postgres-read-replica-1" \
      "$trace_id" \
      "$inv_span" \
      "SELECT stock_qty FROM inventory WHERE sku=?" \
      "$inv_db_dur" \
      0 \
      "db.system=\"postgresql\",db.operation=\"SELECT\",db.table=\"inventory\"" \
      200
    
    local price_span=$(hex_id 8)
    latency_mult=$(get_latency_multiplier "pricing-engine" "$region")
    local price_dur=$(apply_latency $(rand 25 70) "$latency_mult")
    
    send_span \
      "pricing-engine" \
      "$trace_id" \
      "$cart_span" \
      "price.calculate" \
      "$price_dur" \
      0 \
      "env=\"$env\",cloud.region=\"$region\",pricing.tier=\"$user_tier\"" \
      200
    
    local promo_span=$(hex_id 8)
    local promo_dur=$(apply_latency $(rand 40 100) 1.2)
    send_span \
      "promo-engine" \
      "$trace_id" \
      "$price_span" \
      "applyDiscounts" \
      "$promo_dur" \
      0 \
      "env=\"$env\",cloud.region=\"$region\",promo.applied=BLACK_FRIDAY_2024" \
      200
  fi
}

generate_checkout_transaction_flow() {
  local trace_id=$1
  local parent=$2
  local region=$3
  local env=$4
  local has_error=$5
  local user_tier=$6
  local user_id=$7
  
  local order_span=$(hex_id 8)
  local latency_mult=$(get_latency_multiplier "orders-api" "$region")
  local order_dur=$(apply_latency $(rand 120 350) "$latency_mult")
  
  send_span \
    "orders-api" \
    "$trace_id" \
    "$parent" \
    "order.create" \
    "$order_dur" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",user.id=\"$user_id\",order.total=\$1,247.99" \
    200
  
  local db_lock_contention=$((RANDOM % 100))
  local db_dur
  if [ $db_lock_contention -lt 8 ]; then
    db_dur=$(apply_latency $(rand 800 2500) 1.0)
    send_span \
      "postgres-master" \
      "$trace_id" \
      "$order_span" \
      "BEGIN; INSERT INTO orders VALUES(...); COMMIT;" \
      "$db_dur" \
      0 \
      "db.system=\"postgresql\",db.operation=\"INSERT\",db.table=\"orders\",db.lock_wait_time_ms=1200" \
      200
    echo "       ⚠️  Database lock contention detected"
  else
    db_dur=$(apply_latency $(rand 35 95) 1.0)
    send_span \
      "postgres-master" \
      "$trace_id" \
      "$order_span" \
      "BEGIN; INSERT INTO orders VALUES(...); COMMIT;" \
      "$db_dur" \
      0 \
      "db.system=\"postgresql\",db.operation=\"INSERT\",db.table=\"orders\"" \
      200
  fi
  
  local payment_span=$(hex_id 8)
  local payment_status=0
  local payment_code=200
  local payment_error=""
  
  if is_circuit_open "stripe-payments-api"; then
    CIRCUIT_BREAKER_COUNT=$((CIRCUIT_BREAKER_COUNT + 1))
    send_span \
      "payments-processor" \
      "$trace_id" \
      "$order_span" \
      "payment.process" \
      "50" \
      1 \
      "env=\"$env\",cloud.region=\"$region\",payment.amount=\$1247.99,payment.method=\"card\"" \
      503 \
      "Circuit breaker OPEN for stripe-payments-api"
    echo "       🔌 Payment failed - circuit breaker open"
    return
  fi
  
  latency_mult=$(get_latency_multiplier "payments-processor" "$region")
  local payment_dur=$(apply_latency $(rand 250 900) "$latency_mult")
  
  local payment_failure=$((RANDOM % 100))
  if [ $payment_failure -lt 5 ] || [ $has_error -eq 1 ]; then
    payment_status=1
    payment_code=402
    payment_error="Card declined: insufficient_funds"
    payment_dur=$(apply_latency $(rand 400 1200) 1.0)
  fi
  
  send_span \
    "payments-processor" \
    "$trace_id" \
    "$order_span" \
    "payment.process" \
    "$payment_dur" \
    "$payment_status" \
    "env=\"$env\",cloud.region=\"$region\",payment.amount=\$1247.99,payment.method=\"card\",payment.provider=\"stripe\"" \
    "$payment_code" \
    "$payment_error"
  
  if is_service_degraded "stripe-payments-api" || [ $payment_failure -lt 5 ]; then
    local stripe_dur=$(apply_latency $(rand 500 2500) 2.5)
    local retry_count=$((RANDOM % 3 + 1))
    
    for ((r=1; r<=retry_count; r++)); do
      local retry_status=1
      [ $r -eq $retry_count ] && [ $payment_status -eq 0 ] && retry_status=0
      
      send_span \
        "stripe-payments-api" \
        "$trace_id" \
        "$payment_span" \
        "POST /v1/payment_intents (attempt $r)" \
        "$stripe_dur" \
        "$retry_status" \
        "http.method=\"POST\",net.peer.name=\"api.stripe.com\",retry.attempt=$r" \
        "$payment_code" \
        "$payment_error"
      
      [ $retry_status -eq 0 ] && break
      safe_sleep 0.01
    done
  else
    local stripe_dur=$(apply_latency $(rand 180 750) 1.0)
    send_span \
      "stripe-payments-api" \
      "$trace_id" \
      "$payment_span" \
      "POST /v1/payment_intents" \
      "$stripe_dur" \
      "$payment_status" \
      "http.method=\"POST\",net.peer.name=\"api.stripe.com\"" \
      "$payment_code" \
      "$payment_error"
  fi
  
  if [ $payment_status -eq 0 ]; then
    local fraud_span=$(hex_id 8)
    local fraud_dur=$(apply_latency $(rand 80 200) 1.0)
    local fraud_score=$((RANDOM % 100))
    local fraud_risk="low"
    [ $fraud_score -gt 70 ] && fraud_risk="medium"
    [ $fraud_score -gt 90 ] && fraud_risk="high"
    
    send_span \
      "fraud-detection" \
      "$trace_id" \
      "$payment_span" \
      "analyzeFraudRisk" \
      "$fraud_dur" \
      0 \
      "env=\"$env\",fraud.score=$fraud_score,fraud.risk=\"$fraud_risk\"" \
      200
    
    local inv_span=$(hex_id 8)
    latency_mult=$(get_latency_multiplier "inventory-mgmt" "$region")
    local inv_dur=$(apply_latency $(rand 45 110) "$latency_mult")
    
    send_span \
      "inventory-mgmt" \
      "$trace_id" \
      "$order_span" \
      "stock.reserve" \
      "$inv_dur" \
      0 \
      "env=\"$env\",cloud.region=\"$region\",items.count=3" \
      200
    
    local inv_update_dur=$(apply_latency $(rand 30 85) 1.0)
    send_span \
      "postgres-master" \
      "$trace_id" \
      "$inv_span" \
      "UPDATE inventory SET reserved=reserved+3 WHERE..." \
      "$inv_update_dur" \
      0 \
      "db.system=\"postgresql\",db.operation=\"UPDATE\",db.table=\"inventory\"" \
      200
    
    local tax_span=$(hex_id 8)
    local tax_dur=$(apply_latency $(rand 150 400) 1.5)
    
    local tax_timeout=$((RANDOM % 100))
    if [ $tax_timeout -lt 3 ]; then
      send_span \
        "tax-calculator" \
        "$trace_id" \
        "$order_span" \
        "calculateSalesTax" \
        "8000" \
        2 \
        "env=\"$env\",cloud.region=\"$region\"" \
        504 \
        "Request to taxjar-api timed out"
    else
      send_span \
        "tax-calculator" \
        "$trace_id" \
        "$order_span" \
        "calculateSalesTax" \
        "$tax_dur" \
        0 \
        "env=\"$env\",cloud.region=\"$region\",tax.amount=\$124.79" \
        200
      
      local taxjar_dur=$(apply_latency $(rand 120 350) 1.0)
      send_span \
        "taxjar-api" \
        "$trace_id" \
        "$tax_span" \
        "POST /v2/taxes" \
        "$taxjar_dur" \
        0 \
        "http.method=\"POST\",net.peer.name=\"api.taxjar.com\"" \
        200
    fi
    
    local ship_span=$(hex_id 8)
    latency_mult=$(get_latency_multiplier "fulfillment-svc" "$region")
    local ship_dur=$(apply_latency $(rand 60 180) "$latency_mult")
    
    send_span \
      "fulfillment-svc" \
      "$trace_id" \
      "$order_span" \
      "shipment.create" \
      "$ship_dur" \
      0 \
      "env=\"$env\",cloud.region=\"$region\",carrier=\"fedex\"" \
      200
    
    local ship_db_dur=$(apply_latency $(rand 25 70) 1.0)
    send_span \
      "postgres-master" \
      "$trace_id" \
      "$ship_span" \
      "INSERT INTO shipments VALUES(...)" \
      "$ship_db_dur" \
      0 \
      "db.system=\"postgresql\",db.operation=\"INSERT\",db.table=\"shipments\"" \
      200
    
    local shipstation_dur=$(apply_latency $(rand 200 600) 1.3)
    send_span \
      "shipstation-api" \
      "$trace_id" \
      "$ship_span" \
      "POST /shipments" \
      "$shipstation_dur" \
      0 \
      "http.method=\"POST\",net.peer.name=\"api.shipstation.com\"" \
      201
    
    local notif_span=$(hex_id 8)
    latency_mult=$(get_latency_multiplier "notifications-hub" "$region")
    local notif_dur=$(apply_latency $(rand 35 100) "$latency_mult")
    
    send_span \
      "notifications-hub" \
      "$trace_id" \
      "$order_span" \
      "notification.queue" \
      "$notif_dur" \
      0 \
      "env=\"$env\",cloud.region=\"$region\",notification.type=\"order_confirmation\"" \
      200
    
    local email_span=$(hex_id 8)
    local email_dur=$(apply_latency $(rand 60 220) 1.0)
    
    send_span \
      "email-dispatcher" \
      "$trace_id" \
      "$notif_span" \
      "email.send" \
      "$email_dur" \
      0 \
      "env=\"$env\",cloud.region=\"$region\",template=\"order_confirmation\"" \
      200
    
    local sendgrid_dur=$(apply_latency $(rand 150 500) 1.0)
    local sendgrid_status=0
    local sendgrid_code=202
    
    local sendgrid_issue=$((RANDOM % 100))
    if [ $sendgrid_issue -lt 4 ]; then
      sendgrid_status=1
      sendgrid_code=429
      sendgrid_dur=$(apply_latency $(rand 300 800) 1.0)
      send_span \
        "sendgrid-smtp" \
        "$trace_id" \
        "$email_span" \
        "POST /v3/mail/send" \
        "$sendgrid_dur" \
        "$sendgrid_status" \
        "http.method=\"POST\",net.peer.name=\"api.sendgrid.com\"" \
        "$sendgrid_code" \
        "Rate limit exceeded - queued for retry"
    else
      send_span \
        "sendgrid-smtp" \
        "$trace_id" \
        "$email_span" \
        "POST /v3/mail/send" \
        "$sendgrid_dur" \
        0 \
        "http.method=\"POST\",net.peer.name=\"api.sendgrid.com\"" \
        202
    fi
    
    local kafka_dur=$(apply_latency $(rand 12 45) 1.0)
    send_span \
      "kafka-cluster" \
      "$trace_id" \
      "$order_span" \
      "PRODUCE topic:order.completed" \
      "$kafka_dur" \
      0 \
      "messaging.system=\"kafka\",messaging.destination=\"order.completed\",messaging.partition=2" \
      200
    
    local analytics_span=$(hex_id 8)
    local analytics_dur=$(apply_latency $(rand 18 60) 1.0)
    
    send_span \
      "event-tracker" \
      "$trace_id" \
      "$parent" \
      "event.track" \
      "$analytics_dur" \
      0 \
      "env=\"$env\",event.name=\"checkout_completed\",event.value=1247.99" \
      200
    
    local sqs_dur=$(apply_latency $(rand 25 90) 1.0)
    send_span \
      "aws-sqs-queue" \
      "$trace_id" \
      "$analytics_span" \
      "SendMessage analytics-events" \
      "$sqs_dur" \
      0 \
      "messaging.system=\"sqs\",messaging.destination=\"analytics-events\"" \
      200
  fi
}

generate_user_data_flow() {
  local trace_id=$1
  local parent=$2
  local region=$3
  local env=$4
  local has_error=$5
  local method=$6
  local user_id=$7
  
  local profile_span=$(hex_id 8)
  local latency_mult=$(get_latency_multiplier "user-profile-api" "$region")
  local profile_dur=$(apply_latency $(rand 35 100) "$latency_mult")
  
  local operation="getProfile"
  [ "$method" == "PUT" ] && operation="updateProfile"
  
  send_span \
    "user-profile-api" \
    "$trace_id" \
    "$parent" \
    "profile.$operation" \
    "$profile_dur" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",user.id=\"$user_id\"" \
    200
  
  local db_operation="SELECT"
  local db_table="user_profiles"
  [ "$method" == "PUT" ] && db_operation="UPDATE"
  
  local db_choice=$((RANDOM % 2))
  local db_service="postgres-read-replica-1"
  [ "$method" == "PUT" ] && db_service="postgres-master"
  
  local db_dur=$(apply_latency $(rand 20 65) 1.0)
  send_span \
    "$db_service" \
    "$trace_id" \
    "$profile_span" \
    "$db_operation FROM $db_table WHERE user_id=$user_id" \
    "$db_dur" \
    0 \
    "db.system=\"postgresql\",db.operation=\"$db_operation\",db.table=\"$db_table\"" \
    200
  
  local s3_dur=$(apply_latency $(rand 50 150) 1.2)
  local s3_operation="GetObject"
  [ "$method" == "PUT" ] && s3_operation="PutObject"
  
  send_span \
    "s3-object-store" \
    "$trace_id" \
    "$profile_span" \
    "$s3_operation avatars/$user_id.jpg" \
    "$s3_dur" \
    0 \
    "aws.service=\"s3\",aws.operation=\"$s3_operation\",aws.bucket=\"user-avatars\"" \
    200
  
  local cdn_dur=$(apply_latency $(rand 15 50) 1.0)
  send_span \
    "cloudfront-cdn" \
    "$trace_id" \
    "$profile_span" \
    "GET /static/profile-assets" \
    "$cdn_dur" \
    0 \
    "cdn.cache_status=\"HIT\",http.url=\"d111111abcdef8.cloudfront.net\"" \
    200
  
  if [ "$method" == "PUT" ]; then
    local cache_invalidate_dur=$(apply_latency $(rand 8 25) 1.0)
    send_span \
      "redis-primary" \
      "$trace_id" \
      "$profile_span" \
      "DEL profile:$user_id" \
      "$cache_invalidate_dur" \
      0 \
      "db.system=\"redis\",db.operation=\"DEL\"" \
      200
  fi
}

generate_order_history_flow() {
  local trace_id=$1
  local parent=$2
  local region=$3
  local env=$4
  local has_error=$5
  local user_id=$6
  
  local orders_span=$(hex_id 8)
  local latency_mult=$(get_latency_multiplier "orders-api" "$region")
  local orders_dur=$(apply_latency $(rand 60 180) "$latency_mult")
  
  send_span \
    "orders-api" \
    "$trace_id" \
    "$parent" \
    "order.listHistory" \
    "$orders_dur" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",user.id=\"$user_id\",limit=50" \
    200
  
  local use_cache=$((RANDOM % 100))
  if [ $use_cache -lt 60 ]; then
    local memcached_dur=$(apply_latency $(rand 4 15) 1.0)
    send_span \
      "memcached-cluster" \
      "$trace_id" \
      "$orders_span" \
      "GET orders:history:$user_id" \
      "$memcached_dur" \
      0 \
      "db.system=\"memcached\",db.operation=\"GET\",cache.hit=true" \
      200
  else
    local db_dur=$(apply_latency $(rand 100 350) 1.3)
    send_span \
      "postgres-read-replica-2" \
      "$trace_id" \
      "$orders_span" \
      "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT 50" \
      "$db_dur" \
      0 \
      "db.system=\"postgresql\",db.operation=\"SELECT\",db.table=\"orders\",cache.miss=true" \
      200
    
    echo "       ℹ️  Cache miss - fetched from database"
    
    local cache_write_dur=$(apply_latency $(rand 6 20) 1.0)
    send_span \
      "memcached-cluster" \
      "$trace_id" \
      "$orders_span" \
      "SET orders:history:$user_id TTL=300" \
      "$cache_write_dur" \
      0 \
      "db.system=\"memcached\",db.operation=\"SET\"" \
      200
  fi
  
  local shipment_span=$(hex_id 8)
  local shipment_dur=$(apply_latency $(rand 40 120) 1.0)
  
  send_span \
    "fulfillment-svc" \
    "$trace_id" \
    "$orders_span" \
    "shipment.getTracking" \
    "$shipment_dur" \
    0 \
    "env=\"$env\",cloud.region=\"$region\",shipments.count=12" \
    200
  
  local mongo_dur=$(apply_latency $(rand 30 90) 1.0)
  send_span \
    "mongodb-shard-1" \
    "$trace_id" \
    "$shipment_span" \
    "find({user_id: '$user_id'})" \
    "$mongo_dur" \
    0 \
    "db.system=\"mongodb\",db.operation=\"find\",db.collection=\"shipments\"" \
    200
}

generate_ml_recommendations_flow() {
  local trace_id=$1
  local parent=$2
  local region=$3
  local env=$4
  local has_error=$5
  local user_id=$6
  
  local rec_span=$(hex_id 8)
  local latency_mult=$(get_latency_multiplier "ml-recommendations" "$region")
  
  local model_cold_start=$((RANDOM % 100))
  local rec_dur
  if [ $model_cold_start -lt 5 ]; then
    rec_dur=$(apply_latency $(rand 2000 5000) 1.5)
    send_span \
      "ml-recommendations" \
      "$trace_id" \
      "$parent" \
      "model.predict" \
      "$rec_dur" \
      0 \
      "env=\"$env\",cloud.region=\"$region\",user.id=\"$user_id\",model.version=\"v2.3\",model.cold_start=true" \
      200
    echo "       🧊 ML model cold start - loading model into memory"
  else
    rec_dur=$(apply_latency $(rand 100 300) "$latency_mult")
    send_span \
      "ml-recommendations" \
      "$trace_id" \
      "$parent" \
      "model.predict" \
      "$rec_dur" \
      0 \
      "env=\"$env\",cloud.region=\"$region\",user.id=\"$user_id\",model.version=\"v2.3\",recommendations.count=10" \
      200
  fi
  
  local feature_dur=$(apply_latency $(rand 60 180) 1.0)
  send_span \
    "postgres-read-replica-1" \
    "$trace_id" \
    "$rec_span" \
    "SELECT user_features, browsing_history FROM..." \
    "$feature_dur" \
    0 \
    "db.system=\"postgresql\",db.operation=\"SELECT\",db.table=\"user_features\"" \
    200
  
  local redis_dur=$(apply_latency $(rand 5 18) 1.0)
  send_span \
    "redis-primary" \
    "$trace_id" \
    "$rec_span" \
    "GET recommendations:cached:$user_id" \
    "$redis_dur" \
    0 \
    "db.system=\"redis\",db.operation=\"GET\",cache.hit=false" \
    200
}

echo "═══════════════════════════════════════════════════════"
echo "  Realistic Distributed Trace Generator"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "Configuration:"
echo "  Endpoint: $ENDPOINT"
echo "  Traces: $COUNT"
echo "  Delay: ${DELAY}s between traces"
echo ""
echo "Press Ctrl+C to stop"
echo ""

for ((i=1;i<=COUNT;i++)); do
  update_global_state
  
  TRACE_ID=$(hex_id 16)
  REGION="${REGIONS[$((RANDOM % ${#REGIONS[@]}))]}"
  ENV="${ENVS[$((RANDOM % ${#ENVS[@]}))]}"
  CUSTOMER="${CUSTOMERS[$((RANDOM % ${#CUSTOMERS[@]}))]}"
  USER_TIER="${USER_TIERS[$((RANDOM % ${#USER_TIERS[@]}))]}"
  
  generate_user_journey "$TRACE_ID" "$REGION" "$ENV" "$CUSTOMER" "$USER_TIER"
  
  safe_sleep "$DELAY"
  
  if (( i % 25 == 0 )); then
    echo ""
    echo "─────────────────────────────────────────────────────"
    echo "📊 Progress: $i/$COUNT traces completed"
    echo "   Errors: $ERROR_COUNT | Timeouts: $TIMEOUT_COUNT | Circuit Breaks: $CIRCUIT_BREAKER_COUNT"
    if [ ${#GLOBAL_STATE_DEGRADED_SERVICES[@]} -gt 0 ]; then
      echo "   ⚠️  Degraded Services: ${GLOBAL_STATE_DEGRADED_SERVICES[*]}"
    fi
    if [ ${#GLOBAL_STATE_CIRCUIT_OPEN[@]} -gt 0 ]; then
      echo "   ⚡ Open Circuits: ${GLOBAL_STATE_CIRCUIT_OPEN[*]}"
    fi
    if [ ${#GLOBAL_STATE_HIGH_LATENCY_REGIONS[@]} -gt 0 ]; then
      echo "   🌐 High Latency Regions: ${GLOBAL_STATE_HIGH_LATENCY_REGIONS[*]}"
    fi
    echo "─────────────────────────────────────────────────────"
    echo ""
  fi
done

echo ""
echo "═══════════════════════════════════════════════════════"
echo "✅ Trace Generation Complete"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "Final Statistics:"
echo "  Total Traces: $COUNT"
echo "  Errors: $ERROR_COUNT"
echo "  Timeouts: $TIMEOUT_COUNT"
echo "  Circuit Breaker Trips: $CIRCUIT_BREAKER_COUNT"
echo "  Error Rate: $(awk "BEGIN {printf \"%.2f%%\", ($ERROR_COUNT/$COUNT)*100}")"
echo ""