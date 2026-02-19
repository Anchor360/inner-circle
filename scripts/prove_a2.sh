#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"

# Best practice: API key from env, safe default for proof harness
API_KEY="${MIC_API_KEY:-DEVKEY_PROOF}"

KEY="prove-a2-key-1"
BODY='{"content":"Proof script claim"}'

echo "== MIC A2/A3 Proof Script =="

echo "[0] Preconditions"
echo "BASE_URL=$BASE_URL"
echo "MIC_API_KEY=$API_KEY (from env MIC_API_KEY or default DEVKEY_PROOF)"
echo

echo "[1] Missing API key should return 401"
STATUS_NO_KEY=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/claims" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $KEY" \
  -d "$BODY")
echo "status=$STATUS_NO_KEY"
if [ "$STATUS_NO_KEY" != "401" ]; then
  echo "FAIL: expected 401 for missing API key"
  exit 1
fi
echo "PASS"
echo

echo "[2] Invalid API key should return 401"
STATUS_BAD_KEY=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/claims" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $KEY" \
  -H "X-Api-Key: BADKEY" \
  -d "$BODY")
echo "status=$STATUS_BAD_KEY"
if [ "$STATUS_BAD_KEY" != "401" ]; then
  echo "FAIL: expected 401 for invalid API key"
  exit 1
fi
echo "PASS"
echo

echo "[3] Create claim with valid API key (expect 200)"
RESP1=$(curl -s -X POST "$BASE_URL/claims" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $KEY" \
  -H "X-Api-Key: $API_KEY" \
  -d "$BODY")

echo "$RESP1"

CLAIM_ID=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['claim_id'])" "$RESP1")
echo "claim_id=$CLAIM_ID"
echo

echo "[4] Replay same request (must match exactly)"
RESP2=$(curl -s -X POST "$BASE_URL/claims" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $KEY" \
  -H "X-Api-Key: $API_KEY" \
  -d "$BODY")

if [ "$RESP1" != "$RESP2" ]; then
  echo "FAIL: replay mismatch"
  exit 1
fi
echo "PASS"
echo

echo "[5] Event count should be 1 for this claim"
COUNT=$(docker exec -i mic-postgres psql -U mic -d mic -t -A -c \
  "SELECT COUNT(*) FROM events WHERE aggregate_type='claim' AND aggregate_id='${CLAIM_ID}';")
echo "event_count=$COUNT"
if [ "$COUNT" != "1" ]; then
  echo "FAIL: duplicate event detected"
  exit 1
fi
echo "PASS"
echo

echo "== ALL PROOFS PASSED =="