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
5. Status transitions to `decomposed`
6. Validation becomes available
7. Verdicts are computed asynchronously
### Claim.decomposition_status — State Transition Table (Normative)

This table defines the authoritative state machine for asynchronous claim decomposition.
Transitions MUST be enforced atomically and MUST be idempotent.

| From | Event | To | Actor | Invariant |
|------|-------|----|-------|-----------|
| — | CreateClaim | pending | API | Claim persisted atomically |
| pending | EnqueueDecomposition | queued | Orchestrator | Enqueue is idempotent |
| queued | WorkerLeaseAcquired | in_progress | Worker | Single active lease |
| in_progress | DecompositionSucceeded | decomposed | Worker | TruthBits written first |
| in_progress | DecompositionFailed | failed | Worker | Failure reason recorded |
| failed | RetryEnqueue | queued | Orchestrator | Retry policy external |
| queued | LeaseTimeout | queued | System | Safe re-lease |
| in_progress | LeaseTimeout | queued | System | Idempotent reprocessing |

**Terminal states:** `decomposed`, `failed`  
**Non-terminal states:** `pending`, `queued`, `in_progress`
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
