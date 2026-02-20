"""
Log generator for testing OTLP log ingestion, simulating realistic log data from a variety of services, environments, and regions. This script generates logs with different severity levels (INFO, WARN, ERROR, DEBUG) based on configurable probabilities that reflect typical distributions in production, staging, and development environments. Each log entry includes attributes such as service name, version, environment, region, host, HTTP method and route, status code, duration, request ID, and trace ID. The script sends the generated logs to the specified OTLP endpoint in batches with configurable parallelism and loop count.

Copyright (c) 2026 Stefan Kumarasinghe

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
"""

#!/usr/bin/env python3
import sys, time, random, secrets, json, threading
from urllib.request import urlopen, Request
from urllib.error import URLError

ENDPOINT = sys.argv[1] if len(sys.argv) > 1 else "localhost:4318"
COUNT    = int(sys.argv[2]) if len(sys.argv) > 2 else 500
PARALLEL = int(sys.argv[3]) if len(sys.argv) > 3 else 12
LOOPS    = int(sys.argv[4]) if len(sys.argv) > 4 else 0  # 0 = infinite

SERVICES = [
    ("payment-service",      "v2.3.1"),
    ("order-service",        "v1.8.4"),
    ("auth-service",         "v3.1.0"),
    ("inventory-service",    "v2.0.7"),
    ("notification-service", "v1.5.2"),
    ("api-gateway",          "v4.2.1"),
    ("catalog-service",      "v2.1.3"),
    ("shipping-service",     "v1.9.0"),
    ("search-service",       "v3.0.5"),
    ("fraud-detection",      "v2.4.1"),
    ("analytics-service",    "v1.7.3"),
    ("checkout-service",     "v2.2.0"),
    ("billing-service",      "v1.4.6"),
    ("gateway-service",      "v3.3.2"),
    ("messaging-service",    "v2.0.1"),
]

REGIONS = ["us-east-1","us-west-2","eu-west-1","eu-central-1","ap-southeast-1","ap-northeast-1",
           "eu-north-1","ap-southeast-2","eu-west-3","eu-central-2","us-east-2","us-west-1"]
ENVS    = ["prod"]*4 + ["staging"]*2 + ["dev"]

SERVICE_ENDPOINTS = {
    "payment-service":      ["POST /v1/charges","POST /v1/refunds","GET /v1/charges/{id}","POST /v1/payment-methods","GET /v1/balance"],
    "order-service":        ["POST /v1/orders","GET /v1/orders/{id}","PATCH /v1/orders/{id}","GET /v1/orders","POST /v1/orders/{id}/cancel"],
    "auth-service":         ["POST /v1/auth/login","POST /v1/auth/refresh","POST /v1/auth/logout","GET /v1/auth/me","POST /v1/auth/verify"],
    "inventory-service":    ["GET /v1/inventory/{sku}","PUT /v1/inventory/{sku}/reserve","GET /v1/inventory","POST /v1/inventory/bulk"],
    "notification-service": ["POST /v1/notifications/email","POST /v1/notifications/sms","POST /v1/notifications/push","GET /v1/notifications/{id}/status"],
    "api-gateway":          ["GET /api/v1/products","POST /api/v1/cart","GET /api/v1/cart","POST /api/v1/checkout","GET /api/v1/orders"],
    "catalog-service":      ["GET /v1/products","GET /v1/products/{id}","GET /v1/categories","GET /v1/products/search","PUT /v1/products/{id}"],
    "shipping-service":     ["POST /v1/shipments","GET /v1/shipments/{id}","GET /v1/rates","POST /v1/labels","GET /v1/tracking/{id}"],
    "search-service":       ["GET /v1/search","POST /v1/search/suggest","POST /v1/index","DELETE /v1/index/{id}","GET /v1/search/facets"],
    "fraud-detection":      ["POST /v1/analyze","GET /v1/rules","POST /v1/flag","GET /v1/score/{id}","POST /v1/feedback"],
    "analytics-service":    ["POST /v1/events","GET /v1/reports","GET /v1/metrics","POST /v1/batch","GET /v1/dashboards/{id}"],
    "checkout-service":     ["POST /v1/checkout","GET /v1/checkout/{id}","POST /v1/checkout/{id}/confirm","DELETE /v1/checkout/{id}"],
    "billing-service":      ["POST /v1/invoices","GET /v1/invoices/{id}","POST /v1/subscriptions","GET /v1/subscriptions/{id}","POST /v1/billing/retry"],
    "gateway-service":      ["GET /health","POST /v1/route","GET /v1/config","POST /v1/auth","GET /v1/metrics"],
    "messaging-service":    ["POST /v1/messages","GET /v1/messages/{id}","POST /v1/topics","GET /v1/topics","POST /v1/subscribe"],
}

SERVICE_MESSAGES = {
    "INFO": {
        "payment-service":      ["Payment authorized","Refund processed","Payment method tokenized","Settlement batch submitted","3DS verification completed"],
        "order-service":        ["Order created","Order status updated","Order shipped","Payment captured","Inventory reserved"],
        "auth-service":         ["User authenticated","Token refreshed","Session created","Token validated","User logged out"],
        "inventory-service":    ["Stock level checked","Reservation confirmed","Inventory updated","Reorder triggered"],
        "notification-service": ["Email delivered","SMS sent","Push notification delivered","Webhook acknowledged"],
        "api-gateway":          ["Request proxied","Cache hit","Request authenticated","Response compressed"],
        "catalog-service":      ["Product retrieved","Search index updated","Category loaded","Cache refreshed"],
        "shipping-service":     ["Shipment created","Label generated","Tracking updated","Rate calculated"],
        "search-service":       ["Search completed","Index updated","Suggestion returned","Facets computed"],
        "fraud-detection":      ["Transaction scored","Rule evaluated","Low risk confirmed","Model inference complete"],
        "analytics-service":    ["Event tracked","Report generated","Metrics aggregated","Batch processed"],
        "checkout-service":     ["Checkout initiated","Order confirmed","Cart validated","Session persisted"],
        "billing-service":      ["Invoice created","Subscription renewed","Payment scheduled","Receipt sent"],
        "gateway-service":      ["Request routed","Config reloaded","Health check passed","Auth delegated"],
        "messaging-service":    ["Message published","Topic created","Subscriber notified","Queue flushed"],
    },
    "WARN": {
        "payment-service":      ["Payment retry attempt","High value transaction flagged","Card expiry approaching","Fraud score elevated"],
        "order-service":        ["Order processing slow","Inventory allocation delayed","Carrier API slow","Partial fulfillment required"],
        "auth-service":         ["Multiple failed logins","Token expiry approaching","Unusual login location","Rate limit approaching"],
        "inventory-service":    ["Low stock threshold reached","Reservation expiring","Sync lag detected","Discrepancy detected"],
        "notification-service": ["Email bounce rate elevated","SMS delivery delayed","Push token expired","Retry queue growing"],
        "api-gateway":          ["Upstream latency spike","Cache hit rate dropping","Backend unhealthy","Connection pool at 80%"],
        "catalog-service":      ["Search index stale","Product data incomplete","Cache eviction rate high","CDN latency elevated"],
        "shipping-service":     ["Carrier API slow","Rate estimate stale","Label generation delayed","Tracking update overdue"],
        "search-service":       ["Index lag detected","Query timeout approaching","Recall degraded","Reindex required"],
        "fraud-detection":      ["Model staleness warning","High false positive rate","Rule conflict detected","Score threshold breached"],
        "analytics-service":    ["Event pipeline lag","Report generation slow","Data gap detected","Buffer near capacity"],
        "checkout-service":     ["Session expiry approaching","Payment provider slow","Cart stale","Retry threshold hit"],
        "billing-service":      ["Dunning cycle starting","Payment method expiring","Invoice overdue","Retry limit approaching"],
        "gateway-service":      ["Circuit breaker approaching","Deprecated route called","Config drift detected","TLS cert expiring"],
        "messaging-service":    ["Consumer lag growing","Dead letter queue filling","Broker backpressure","Partition rebalancing"],
    },
    "ERROR": {
        "payment-service":      ["Payment gateway timeout","Card declined by issuer","Duplicate transaction","Tokenization unavailable","Fraud check failed"],
        "order-service":        ["Inventory reservation failed","Payment authorization expired","Carrier API unavailable","DB write timeout"],
        "auth-service":         ["Invalid credentials","Token signature invalid","Session store unreachable","OAuth provider timeout","Account locked"],
        "inventory-service":    ["Insufficient stock","Reservation conflict","Database deadlock","Warehouse API down","SKU not found"],
        "notification-service": ["Email provider unavailable","SMS gateway auth failed","Template rendering failed","All providers failed"],
        "api-gateway":          ["Upstream connection refused","Circuit breaker open","Request timeout","Authentication failed"],
        "catalog-service":      ["Search service unavailable","DB query timeout","Product not found","Index corruption detected"],
        "shipping-service":     ["Carrier API down","Label service unavailable","Rate fetch failed","Invalid address"],
        "search-service":       ["Index unavailable","Query parse failed","Shard timeout","Storage full"],
        "fraud-detection":      ["Model inference failed","Rules engine timeout","Database unreachable","Score unavailable"],
        "analytics-service":    ["Pipeline failure","Storage write failed","Aggregation timeout","Schema mismatch"],
        "checkout-service":     ["Session expired","Payment service down","Cart conflict","Validation failed"],
        "billing-service":      ["Invoice generation failed","Subscription state invalid","Payment provider down","Retry exhausted"],
        "gateway-service":      ["All upstreams unhealthy","Config load failed","Certificate expired","Auth service unreachable"],
        "messaging-service":    ["Broker unreachable","Publish timeout","Consumer crash","Partition unavailable"],
    },
    "DEBUG": {
        "default": ["Cache lookup","DB query executed","Span started","Config read","Lock acquired",
                    "Retry scheduled","Connection pooled","Header parsed","Middleware chain complete","Serialization done"],
    },
}

def pick(lst):  return random.choice(lst)
def rand(a, b): return random.randint(a, b)

def get_level(env):
    r = rand(1, 100)
    if env == "prod":
        if r <= 2:  return "ERROR"
        if r <= 8:  return "WARN"
        if r <= 15: return "DEBUG"
        return "INFO"
    if env == "staging":
        if r <= 5:  return "ERROR"
        if r <= 15: return "WARN"
        if r <= 35: return "DEBUG"
        return "INFO"
    if r <= 10: return "ERROR"
    if r <= 25: return "WARN"
    if r <= 50: return "DEBUG"
    return "INFO"

def get_message(level, svc):
    if level == "DEBUG":
        return pick(SERVICE_MESSAGES["DEBUG"]["default"])
    return pick(SERVICE_MESSAGES[level].get(svc, SERVICE_MESSAGES[level].get("api-gateway", ["Operation completed"])))

def get_status(level):
    if level == "ERROR": return pick([400,401,403,404,409,422,429,500,502,503,504])
    if level == "WARN":  return pick([200,200,200,429,503])
    return pick([200,200,200,200,201,201,202,204])

def get_duration(level, endpoint):
    if any(x in endpoint for x in ["search","suggest"]):
        base = rand(50, 200)
    elif any(x in endpoint for x in ["charges","checkout","orders","payment"]):
        base = rand(150, 600)
    else:
        base = rand(20, 120)
    if level == "ERROR":                      base *= rand(3, 8)
    elif level == "WARN" and rand(1,3) == 1:  base *= 2
    if rand(1, 100) <= 2:                     base *= rand(5, 15)
    return base

def build_payload(svc, version, env, region, host, endpoint, status, duration, level, message, trace_id, request_id):
    method, route = endpoint.split(maxsplit=1)
    attrs = [
        {"key": "service.name",     "value": {"stringValue": svc}},
        {"key": "service.version",  "value": {"stringValue": version}},
        {"key": "env",              "value": {"stringValue": env}},
        {"key": "cloud.region",     "value": {"stringValue": region}},
        {"key": "host.name",        "value": {"stringValue": host}},
        {"key": "http.method",      "value": {"stringValue": method}},
        {"key": "http.route",       "value": {"stringValue": route}},
        {"key": "http.status_code", "value": {"intValue": status}},
        {"key": "duration_ms",      "value": {"intValue": duration}},
        {"key": "request.id",       "value": {"stringValue": request_id}},
    ]
    if level == "ERROR":
        attrs.append({"key": "error.code", "value": {"stringValue": pick(["ECONNREFUSED","ETIMEDOUT","ENOTFOUND","E500","E503","E504"])}})

    return {
        "resourceLogs": [{
            "resource":  {"attributes": [{"key": "service.name", "value": {"stringValue": svc}}]},
            "scopeLogs": [{"scope": {"name": "log-gen"}, "logRecords": [{
                "timeUnixNano":   str(time.time_ns()),
                "severityNumber": {"DEBUG": 5, "INFO": 9, "WARN": 13, "ERROR": 17}[level],
                "severityText":   level,
                "body":           {"stringValue": message},
                "attributes":     attrs,
                "traceId":        trace_id,
            }]}],
        }]
    }

def send(payload):
    data = json.dumps(payload).encode()
    req  = Request(f"http://{ENDPOINT}/v1/logs", data=data,
                   headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=5): pass
        return True
    except URLError as e:
        print(f"  ⚠ send failed: {e}", file=sys.stderr)
        return False

def run_log(i, loop):
    svc, version = pick(SERVICES)
    env          = pick(ENVS)
    region       = pick(REGIONS)
    host         = f"{svc}-{secrets.token_hex(4)}"
    level        = get_level(env)
    endpoint     = pick(SERVICE_ENDPOINTS.get(svc, ["GET /v1/health"]))
    message      = get_message(level, svc)
    status       = get_status(level)
    duration     = get_duration(level, endpoint)
    trace_id     = secrets.token_hex(16)
    request_id   = f"req_{secrets.token_hex(4)}"

    payload = build_payload(svc, version, env, region, host, endpoint,
                            status, duration, level, message, trace_id, request_id)
    ok   = send(payload)
    mark = {"INFO": "✓", "WARN": "⚠", "ERROR": "✗", "DEBUG": "·"}.get(level, "·")
    print(f"[loop={loop} {i:>4}] {mark} {level:<5} | {svc:<24} | {endpoint:<40} | {duration}ms | {status} | {message}")

def run_loop(loop_num):
    print(f"\n{'='*60}")
    print(f"Loop {loop_num} — {COUNT} logs | parallel={PARALLEL}")
    print(f"{'='*60}")
    sem     = threading.Semaphore(PARALLEL)
    threads = []

    def worker(i):
        with sem:
            run_log(i, loop_num)

    for i in range(1, COUNT + 1):
        t = threading.Thread(target=worker, args=(i,), daemon=True)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    print(f"✅ Loop {loop_num} done")

print(f"{'='*60}")
print(f"OTLP Log Generator → http://{ENDPOINT}/v1/logs")
print(f"count={COUNT}  parallel={PARALLEL}  loops={'∞' if LOOPS == 0 else LOOPS}")
print(f"{'='*60}")

loop = 1
while True:
    run_loop(loop)
    if LOOPS != 0 and loop >= LOOPS:
        break
    loop += 1

print(f"\n{'='*60}")
print(f"✅ Done: {loop} loop(s) × {COUNT} logs")
print(f"{'='*60}")