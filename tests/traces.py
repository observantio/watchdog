#!/usr/bin/env python3
import sys, time, random, secrets, json, threading
from urllib.request import urlopen, Request
from urllib.error import URLError

ENDPOINT = sys.argv[1] if len(sys.argv) > 1 else "localhost:4318"
COUNT    = int(sys.argv[2]) if len(sys.argv) > 2 else 500
PARALLEL = int(sys.argv[3]) if len(sys.argv) > 3 else 12
LOOPS    = int(sys.argv[4]) if len(sys.argv) > 4 else 2 
DELAY    = float(sys.argv[5]) if len(sys.argv) > 5 else 0.0

FRONTENDS = ["web-frontend","mobile-ios","mobile-android","admin-portal","partner-portal","merchant-dashboard"]
GATEWAYS  = ["api-gateway","graphql-gateway","grpc-gateway","websocket-gateway"]
SERVICES  = ["order-service","payment-service","inventory-service","shipping-service","pricing-service",
             "catalog-service","cart-service","recommendation-service","search-service",
             "fraud-detection","analytics-service","returns-service","review-service","wishlist-service"]
DBS       = ["postgres-primary","postgres-replica-1","postgres-replica-2","redis-cache","redis-session",
             "mongodb-primary","elasticsearch","cassandra-node-1","s3-storage"]
REGIONS   = ["us-east-1","us-west-2","eu-west-1","eu-central-1","ap-southeast-1","ap-northeast-1"]
ENVS      = ["prod"]*4 + ["staging"]*2 + ["dev"]
CUSTOMERS = ["acme-corp","globex","initech","wayne-enterprises","stark-industries","free-tier","premium-tier","enterprise-tier"]
ROUTES    = [("/api/products","GET"),("/api/cart","POST"),("/api/checkout","POST"),
             ("/api/orders","GET"),("/api/search","GET"),("/api/user/profile","GET"),
             ("/api/reviews","POST"),("/api/wishlist","GET"),("/api/recommendations","GET"),("/graphql","POST")]

def sid(): return secrets.token_hex(8)
def tid(): return secrets.token_hex(16)
def pick(lst): return random.choice(lst)
def rand(a, b): return random.randint(a, b)
def latency(base, var, spike=5):
    return base * rand(3, 8) if rand(1, 100) <= spike else max(1, base + rand(-var//2, var//2))

class Span:
    def __init__(self, trace_id, name, service, duration_ms, parent_id=None, error=False, attrs=None):
        self.trace_id    = trace_id
        self.span_id     = sid()
        self.parent_id   = parent_id
        self.name        = name
        self.service     = service
        self.duration_ms = duration_ms
        self.error       = error
        self.attrs       = attrs or {}

def build_otlp(spans):
    now_ns = time.time_ns()
    by_svc = {}
    for sp in spans:
        by_svc.setdefault(sp.service, []).append(sp)

    resource_spans = []
    for svc, svc_spans in by_svc.items():
        otel_spans = []
        for sp in svc_spans:
            start = now_ns + rand(0, 5_000_000)
            end   = start + sp.duration_ms * 1_000_000
            ospan = {
                "traceId":           sp.trace_id,
                "spanId":            sp.span_id,
                "name":              sp.name,
                "kind":              2,
                "startTimeUnixNano": str(start),
                "endTimeUnixNano":   str(end),
                "attributes":        [{"key": k, "value": {"stringValue": str(v)}} for k, v in sp.attrs.items()],
                "status":            {"code": 2 if sp.error else 1},
            }
            if sp.parent_id:
                ospan["parentSpanId"] = sp.parent_id
            otel_spans.append(ospan)
        resource_spans.append({
            "resource":   {"attributes": [{"key": "service.name", "value": {"stringValue": svc}}]},
            "scopeSpans": [{"scope": {"name": "trace-gen"}, "spans": otel_spans}],
        })
    return {"resourceSpans": resource_spans}

def send(spans):
    payload = json.dumps(build_otlp(spans)).encode()
    req = Request(f"http://{ENDPOINT}/v1/traces", data=payload,
                  headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=5): pass
        return True
    except URLError as e:
        print(f"  ⚠ send failed: {e}", file=sys.stderr)
        return False

def make_trace():
    trace_id   = tid()
    route, method = pick(ROUTES)
    region     = pick(REGIONS)
    env        = pick(ENVS)
    customer   = pick(CUSTOMERS)
    error_rate = {"dev": 15, "staging": 8}.get(env, 3)
    has_error  = rand(1, 100) <= error_rate
    hstatus    = pick([400,401,403,404,422,429,500,502,503]) if has_error else pick([200,200,200,201,204])
    max_spans  = rand(3, 8)
    spans      = []

    def add(name, svc, dur, parent=None, error=False, **attrs):
        if len(spans) >= max_spans:
            return None
        sp = Span(trace_id, name, svc, dur, parent_id=parent, error=error,
                  attrs={"env": env, "cloud.region": region, **attrs})
        spans.append(sp)
        return sp.span_id

    root = add(f"{method} {route}", pick(FRONTENDS), latency(50,60,8), error=has_error,
               **{"http.method": method, "http.route": route, "http.status_code": hstatus, "customer": customer})
    gw   = add(f"{method} {route}", pick(GATEWAYS), latency(80,100,6), parent=root,
               error=has_error, **{"gateway.type": "http"})

    if has_error or not gw:
        return spans

    auth = add("ValidateToken", "auth-service", latency(15,20,3), parent=gw, **{"rpc.system": "grpc"})
    if auth:
        cache_hit = rand(1,100) <= 70
        add("GET session", pick(["redis-cache","redis-session"]), rand(1,6), parent=auth,
            **{"db.system": "redis", "cache.hit": str(cache_hit).lower()})
        if not cache_hit:
            add("SELECT users", pick(["postgres-primary","postgres-replica-1"]), rand(10,30),
                parent=auth, **{"db.system": "postgresql", "db.operation": "SELECT"})

    if route.startswith("/api/product") or route == "/api/search":
        cs = add("GetProducts", "catalog-service", latency(60,80,5), parent=gw, **{"rpc.method": "GetProducts"})
        if cs:
            add(pick(["MGET products:*","SELECT * FROM products LIMIT 50"]),
                pick(["redis-cache","postgres-replica-1"]), rand(5,40), parent=cs, **{"db.operation": "SELECT"})
        add("POST /_search", pick(["elasticsearch","opensearch"]), latency(80,120,12),
            parent=gw, **{"db.system": "elasticsearch"})

    elif route == "/api/cart":
        cs = add("UpdateCart", "cart-service", latency(40,60,6), parent=gw, **{"cart.items": rand(1,10)})
        if cs:
            add("SETEX cart", "redis-cache", rand(2,10), parent=cs, **{"db.system": "redis", "db.operation": "SETEX"})
            add("CheckAvailability", "inventory-service", latency(35,50,8), parent=cs)
            add("CalculatePrice", "pricing-service", latency(25,40,5), parent=cs, **{"pricing.strategy": "dynamic"})

    elif route == "/api/checkout":
        oerr = rand(1,100) <= 5
        os_ = add("CreateOrder", "order-service", latency(150,200,10), parent=gw, error=oerr,
                  **{"order.total": rand(50,5000), "order.currency": "USD"})
        if os_ and not oerr:
            add("INSERT INTO orders", "postgres-primary", rand(25,70), parent=os_,
                **{"db.system": "postgresql", "db.operation": "INSERT"})
            add("AnalyzeTransaction", "fraud-detection", latency(80,150,15), parent=os_,
                **{"fraud.score": rand(1,100), "ml.model": "fraud-v3"})
            perr = rand(1,100) <= 4
            prov = pick(["stripe-api","paypal-api"])
            ps = add("ProcessPayment", "payment-service", latency(300,500,25), parent=os_,
                     error=perr, **{"payment.provider": prov})
            if ps:
                add("POST /v1/charges", prov, latency(250,450,30), parent=ps,
                    error=perr, **{"http.method": "POST"})
            if not perr:
                add("CreateShipment", "shipping-service", latency(70,120,10), parent=os_,
                    **{"shipping.carrier": pick(["UPS","FedEx","DHL","USPS"])})
                add("PUBLISH order.created", pick(["kafka-broker-1","kafka-broker-2"]),
                    rand(5,25), parent=os_, **{"messaging.system": "kafka"})

    elif route == "/api/orders":
        os_ = add("GetOrders", "order-service", latency(45,70,7), parent=gw)
        if os_:
            add("SELECT * FROM orders LIMIT 20", pick(["postgres-replica-1","postgres-replica-2"]),
                rand(25,80), parent=os_, **{"db.system": "postgresql", "db.operation": "SELECT"})

    elif route == "/api/user/profile":
        ps = add("GetProfile", "profile-service", latency(40,70,6), parent=gw)
        if ps:
            add("SELECT * FROM user_profiles", pick(["postgres-replica-1","postgres-replica-2"]),
                rand(18,50), parent=ps, **{"db.system": "postgresql", "db.operation": "SELECT"})
            if rand(1,2) == 1:
                add("GET /assets", pick(["s3-storage","cloudflare-cdn"]), latency(30,150,15),
                    parent=ps, **{"aws.service": "s3"})
    else:
        svc = pick(SERVICES)
        sp  = add("ProcessRequest", svc, latency(40,100,10), parent=gw, **{"rpc.method": "ProcessRequest"})
        if sp:
            add(pick(["SELECT","INSERT","UPDATE"]), pick(DBS), rand(15,70), parent=sp, **{"db.operation": "query"})

    return spans

def run_trace(i, loop):
    spans = make_trace()
    ok    = send(spans)
    mark  = "✓" if ok else "✗"
    t     = spans[0].trace_id[:12] if spans else "?"
    print(f"[loop={loop} {i:>4}] {mark} trace={t}… spans={len(spans)}")

def run_loop(loop_num):
    print(f"\n{'='*48}")
    print(f"Loop {loop_num} — {COUNT} traces | parallel={PARALLEL}")
    print(f"{'='*48}")
    sem     = threading.Semaphore(PARALLEL)
    threads = []

    def worker(i):
        with sem:
            run_trace(i, loop_num)

    for i in range(1, COUNT + 1):
        t = threading.Thread(target=worker, args=(i,), daemon=True)
        t.start()
        threads.append(t)
        if DELAY > 0:
            time.sleep(DELAY)

    for t in threads:
        t.join()

    print(f"✅ Loop {loop_num} done")

print(f"{'='*48}")
print(f"OTLP Trace Generator → http://{ENDPOINT}/v1/traces")
print(f"count={COUNT}  parallel={PARALLEL}  loops={'∞' if LOOPS == 0 else LOOPS}  delay={DELAY}s")
print(f"{'='*48}")

loop = 1
while True:
    run_loop(loop)
    if LOOPS != 0 and loop >= LOOPS:
        break
    loop += 1

print(f"\n{'='*48}")
print(f"✅ Done: {loop} loop(s) × {COUNT} traces")
print(f"{'='*48}")
