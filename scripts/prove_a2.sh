#!/usr/bin/env bash
set -euo pipefail

BASE_URL="http://127.0.0.1:8000"
API_KEY_VALID="DEVKEY123"
API_KEY_INVALID="BADKEY000"
IDEMPOTENCY_KEY="demo-key-ps-1"
BODY='{"content":"Proof script claim"}'

echo "== MIC A2 Proof Script =="

echo "[0a] Missing X-Api-Key should be 401"
STATUS_MISSING=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/claims" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: missing-key-test" \
  -d "$BODY")
echo "status=$STATUS_MISSING"
if [ "$STATUS_MISSING" != "401" ]; then
  echo "FAIL: expected 401 on missing X-Api-Key"
  exit 1
fi
echo "PASS"

echo "[0b] Invalid X-Api-Key should be 401"
STATUS_INVALID=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/claims" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: $API_KEY_INVALID" \
  -H "Idempotency-Key: invalid-key-test" \
  -d "$BODY")
echo "status=$STATUS_INVALID"
if [ "$STATUS_INVALID" != "401" ]; then
  echo "FAIL: expected 401 on invalid X-Api-Key"
  exit 1
fi
echo "PASS"

echo "[1] Create claim"
RESP1=$(curl -s -X POST "$BASE_URL/claims" -H "Content-Type: application/json" -H "X-Api-Key: $API_KEY_VALID" -H "Idempotency-Key: $IDEMPOTENCY_KEY" -d "$BODY")
echo "$RESP1"

CLAIM_ID=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['claim_id'])" "$RESP1")
echo "claim_id=$CLAIM_ID"

echo "[2] Replay same request (must match exactly)"
RESP2=$(curl -s -X POST "$BASE_URL/claims" -H "Content-Type: application/json" -H "X-Api-Key: $API_KEY_VALID" -H "Idempotency-Key: $IDEMPOTENCY_KEY" -d "$BODY")
if [ "$RESP1" != "$RESP2" ]; then
  echo "FAIL: replay mismatch"
  exit 1
fi
echo "PASS"

echo "[3] Event count should be 1"
COUNT=$(docker exec -i mic-postgres psql -U mic -d mic -t -A -c "SELECT COUNT(*) FROM events WHERE aggregate_type='claim' AND aggregate_id='${CLAIM_ID}';")
echo "event_count=$COUNT"
if [ "$COUNT" != "1" ]; then
  echo "FAIL: duplicate event detected"
  exit 1
fi
echo "PASS"

echo "== ALL A2 PROOFS PASSED =="