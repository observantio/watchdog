#!/usr/bin/env bash
set -e

BASE_URL="http://192.168.139.120:4319"
PROXY_URL="http://192.168.139.120:8080"

echo "╔════════════════════════════════════════════════════╗"
echo "║   GRAFANA PROXY COMPREHENSIVE TEST SUITE          ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""

# Login as admin
ADMIN_TOKEN=$(curl -s "$BASE_URL/api/auth/login" -H "Content-Type: application/json" -d '{"username":"admin","password":"admin"}' | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
echo "✓ Admin authenticated"
echo ""

# Clean up old test users (skip if fails)
echo "Cleaning up old test users..."
for username in user1 user2 user3; do
    USER_ID=$(curl -s "$BASE_URL/api/auth/users" -H "Authorization: Bearer $ADMIN_TOKEN" 2>/dev/null | python3 -c "import json,sys; users=json.load(sys.stdin) if sys.stdin.read() else [];  u=[x for x in users if x.get('username')=='$username']; print(u[0]['id'] if u else '')" 2>/dev/null || echo "")
    if [[ -n "$USER_ID" ]]; then
        curl -s -X DELETE "$BASE_URL/api/auth/users/$USER_ID" -H "Authorization: Bearer $ADMIN_TOKEN" > /dev/null 2>&1
    fi
done
echo "✓ Cleanup complete"
echo ""

# Create 3 test users
echo "Creating 3 test users..."
for i in 1 2 3; do
    curl -s -X POST "$BASE_URL/api/auth/users" \
        -H "Authorization: Bearer $ADMIN_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"username\":\"user$i\",\"password\":\"password123\",\"email\":\"user$i@test.com\",\"is_admin\":false}" > /dev/null
    
    USER_ID=$(curl -s "$BASE_URL/api/auth/users" -H "Authorization: Bearer $ADMIN_TOKEN" | \
        python3 -c "import json,sys; users=json.load(sys.stdin); u=[x for x in users if x.get('username')=='user$i']; print(u[0]['id'] if u else '')")
    
    curl -s -X PUT "$BASE_URL/api/auth/users/$USER_ID/permissions" \
        -H "Authorization: Bearer $ADMIN_TOKEN" \
        -H "Content-Type: application/json" \
        -d '["write:dashboards","read:dashboards","write:datasources","read:datasources"]' > /dev/null
    
    echo "  ✓ user$i created with write permissions"
done
echo ""

# Test 1: Non-admin dashboard listing (before creating any)
echo "═══ TEST 1: Dashboard Listing (Empty) ═══"
USER1_TOKEN=$(curl -s "$BASE_URL/api/auth/login" -H "Content-Type: application/json" -d '{"username":"user1","password":"password123"}' | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

DASH_COUNT=$(curl -s "$BASE_URL/api/grafana/dashboards/search" -H "Authorization: Bearer $USER1_TOKEN" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d) if isinstance(d, list) else f'ERROR: {d}')")
echo "user1 dashboard count: $DASH_COUNT"
echo ""

# Test 2: Create dashboard for each user
echo "═══ TEST 2: Creating Dashboards ═══"
for i in 1 2 3; do
    USER_TOKEN=$(curl -s "$BASE_URL/api/auth/login" -H "Content-Type: application/json" -d "{\"username\":\"user$i\",\"password\":\"password123\"}" | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
    
    RESULT=$(curl -s -X POST "$BASE_URL/api/grafana/dashboards" \
        -H "Authorization: Bearer $USER_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"dashboard\":{\"title\":\"User${i} Private Dashboard\",\"timezone\":\"browser\"},\"visibility\":\"private\"}")
    
    UID=$(echo "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('uid', 'ERROR'))")
    echo "  ✓ user$i dashboard created: $UID"
    eval "USER${i}_DASH_UID=$UID"
done
echo ""

# Test 3: Non-admin listing their own dashboard
echo "═══ TEST 3: Dashboard Listing (After Creation) ═══"
DASH_LIST=$(curl -s "$BASE_URL/api/grafana/dashboards/search" -H "Authorization: Bearer $USER1_TOKEN")
DASH_COUNT=$(echo "$DASH_LIST" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d) if isinstance(d, list) else f'ERROR: {d}')")
echo "user1 can see $DASH_COUNT dashboard(s)"

if [[ "$DASH_COUNT" == "0" || "$DASH_COUNT" == "ERROR"* ]]; then
    echo "❌ ISSUE FOUND: user1 cannot list their own dashboard"
    echo "   Response: $DASH_LIST" | head -c 200
else
    echo "✓ user1 can list their own dashboard"
    # Check URL field
    URL=$(echo "$DASH_LIST" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0].get('url', 'NO_URL') if d else 'EMPTY')")
    echo "  Dashboard URL field: $URL"
    if [[ "$URL" == "NO_URL" || "$URL" == "/" ]]; then
        echo "  ❌ ISSUE: URL field is empty or incorrect"
    fi
fi
echo ""

# Test 4: Proxy access to own dashboard
echo "═══ TEST 4: Proxy Access to Own Dashboard ═══"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $USER1_TOKEN" "$PROXY_URL/grafana/d/$USER1_DASH_UID")
echo "user1 accessing own dashboard via proxy: HTTP $STATUS"
if [[ "$STATUS" != "200" ]]; then
    echo "❌ ISSUE: Cannot access own dashboard via proxy"
fi
echo ""

# Test 5: Datasource listing
echo "═══ TEST 5: Datasource Listing ═══"
DS_COUNT=$(curl -s "$BASE_URL/api/grafana/datasources" -H "Authorization: Bearer $USER1_TOKEN" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d) if isinstance(d, list) else f'ERROR: {d}')")
echo "user1 can see $DS_COUNT datasource(s)"
echo ""

# Test 6: Admin sees all dashboards
echo "═══ TEST 6: Admin Dashboard Listing ═══"
ADMIN_DASH_COUNT=$(curl -s "$BASE_URL/api/grafana/dashboards/search" -H "Authorization: Bearer $ADMIN_TOKEN" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d) if isinstance(d, list) else len(d))")
echo "Admin sees $ADMIN_DASH_COUNT dashboard(s)"
echo ""

# Test 7: Cross-user access (should be blocked)
echo "═══ TEST 7: Cross-User Access (Security Check) ═══"
USER2_TOKEN=$(curl -s "$BASE_URL/api/auth/login" -H "Content-Type: application/json" -d '{"username":"user2","password":"password123"}' | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $USER2_TOKEN" "$PROXY_URL/grafana/d/$USER1_DASH_UID")
echo "user2 trying to access user1's dashboard: HTTP $STATUS"
if [[ "$STATUS" == "200" ]]; then
    echo "❌ SECURITY ISSUE: user2 can access user1's private dashboard!"
elif [[ "$STATUS" == "403" ]]; then
    echo "✓ Security preserved: user2 blocked from user1's dashboard"
fi
echo ""

echo "╔════════════════════════════════════════════════════╗"
echo "║              TEST SUITE COMPLETE                   ║"
echo "╚════════════════════════════════════════════════════╝"
