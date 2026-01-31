## Execution Model (v0.1)

Inner-Circle operates as an **asynchronous, state-driven system**.

Principles:
- Client requests create or append records
- Background processes advance state
- No client call blocks on long-running work

Execution flow:
1. Client submits a Claim
2. Claim is persisted with `decomposition_status = pending`
3. A background process transitions status to `in_progress`
4. TruthBits are derived and stored
5. Status transitions to `complete`
6. Validation becomes available
7. Verdicts are computed asynchronously

Guarantees:
- All client-facing operations are fast and non-blocking
- State transitions are durable and auditable
- Reprocessing is safe due to idempotency and append-only writes

Non-guarantees (v0.1):
- Ordering across domains
- Real-time completion
- Exactly-once background execution

## Operations (v0.1)

Each operation is defined as a typed method (RPC-style) with an equivalent REST mapping.

### CreateClaim

RPC:
- `CreateClaim(CreateClaimRequest) -> CreateClaimResponse`

REST mapping:
- `POST /v0.1/claims`

Request fields:
- `idempotency_key` (string, required)
- `domain` (string, required)
- `text` (string, required)
- `created_by` (string, optional)

Response fields:
- `claim_id` (string, required)
- `created_at` (timestamp, required)
