#!/usr/bin/env bash
set -euo pipefail

BASE_URL="http://127.0.0.1:8000"
KEY="demo-key-ps-1"
BODY='{"content":"Proof script claim"}'

echo "== MIC A2 Proof Script =="

echo "[1] Create claim"
RESP1=$(curl -s -X POST "$BASE_URL/claims" -H "Content-Type: application/json" -H "Idempotency-Key: $KEY" -d "$BODY")
echo "$RESP1"

CLAIM_ID=$(python -c "import json,sys; print(json.loads(sys.argv[1])['claim_id'])" "$RESP1")
echo "claim_id=$CLAIM_ID"

echo "[2] Replay same request (must match exactly)"
RESP2=$(curl -s -X POST "$BASE_URL/claims" -H "Content-Type: application/json" -H "Idempotency-Key: $KEY" -d "$BODY")
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