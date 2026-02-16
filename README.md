# Inner-Circle (MIC) — Proof of Concept

Inner-Circle is a credibility-first verification infrastructure designed to answer not just *what* is true, but *how confidently* it is known, *where the evidence came from*, and *what remains unknown*.

This Proof of Concept demonstrates a minimal, reproducible verification loop suitable for regulated and high-trust environments (finance, legal, policy, research).

---

## Health Check

Verify the service and database connectivity.

```bash
curl -s http://127.0.0.1:8000/health
Expected

{
  "status": "ok",
  "service": "inner-circle-api"
}
What this proves: the API is running and can communicate with its datastore.

Proof of Concept Demo (Canonical Flow)
This is the authoritative demo path. Follow steps in order.

1) Create a Claim
Register the statement you want to evaluate.

curl -s -X POST http://127.0.0.1:8000/claims \
  -H "Content-Type: application/json" \
  -d '{"content":"Issuer revenue increased 18% year-over-year according to Q4 filing"}'
Response (example)

{
  "claim_id": "CLAIM_ID_HERE",
  "created_at": "2026-02-09T16:42:54.844412Z"
}
What this proves: claims are first-class, addressable objects with stable identifiers.

2) Ensure a Primary Source Exists
This POC uses a seeded primary source (SEC EDGAR).

SOURCE_ID="11111111-1111-1111-1111-111111111111"
What this proves: evidence is evaluated using provenance and authority tiers, not all sources are treated equally.

3) Submit a Sourced Validation
Attach evidence to the claim with outcome, confidence, and source.

CLAIM_ID="CLAIM_ID_HERE"

curl -s -X POST http://127.0.0.1:8000/validations \
  -H "Content-Type: application/json" \
  -d '{
    "claim_id":"'"$CLAIM_ID"'",
    "source_id":"'"$SOURCE_ID"'",
    "outcome":"supports",
    "confidence":0.9,
    "evidence_ref":"sec-edgar-q4-filing"
  }'
What this proves: evidence is stored with explicit provenance and quantified confidence.

4) Review Inputs (Audit View)
Retrieve the claim and all attached validations before any verdict is computed.

curl -s http://127.0.0.1:8000/claims/$CLAIM_ID/validations
What this proves: Inner-Circle exposes inputs transparently prior to producing an output.

5) Compute an Immutable Verdict Snapshot
Compute a verdict derived only from stored validations.

curl -s -X POST http://127.0.0.1:8000/claims/$CLAIM_ID/verdicts/compute
Expected: 201 Created

What this proves (core credibility):

Verdicts are computed from evidence, not guesses

Each verdict is an immutable, time-stamped snapshot

Prior verdicts are never overwritten

6) Retrieve the Latest Verdict (Read-Only)
curl -s http://127.0.0.1:8000/claims/$CLAIM_ID/verdicts/latest
Response (example)

{
  "verdict_id": "...",
  "claim_id": "...",
  "status": "verified",
  "confidence": 0.9,
  "validation_ids": [...],
  "created_at": "..."
}
What this proves: consumers can retrieve the current verdict posture without recomputation.

7) Retrieve Verdict History (Audit Trail)
curl -s http://127.0.0.1:8000/claims/$CLAIM_ID/verdicts
What this proves: verdict posture changes are preserved over time for audit, compliance, and review.

Epistemic Behavior (Important)
Inner-Circle explicitly separates delivery truth from epistemic truth.

HTTP status codes describe whether a resource exists.

Verdict states describe what the system knows, does not know, or refuses to assert.

Example: No Verdict Yet
If no verdict exists for a claim:

curl -s http://127.0.0.1:8000/claims/NEW_CLAIM_ID/verdicts/latest
Response

HTTP 404

{
  "code": "NO_VERDICT",
  "epistemic_status": "unknown",
  "message": "No verdict exists for this claim yet.",
  "next_action": {
    "method": "POST",
    "path": "/claims/NEW_CLAIM_ID/verdicts/compute"
  }
}
What this proves: Inner-Circle explicitly states unknown rather than guessing or fabricating certainty.
