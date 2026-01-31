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

Guarantees (v0.1):
- **Durability:** Once an operation returns success, its primary record write
  is durable (Claim, Evidence, Validation, Verdict).
- **Atomic state transitions:** `Claim.decomposition_status` transitions are
  enforced atomically using compare-and-set semantics.
- **Idempotency:** Retried client calls and retried workers MUST NOT create
  duplicate logical outcomes (e.g., duplicate TruthBits).
- **At-least-once processing:** Background workers may execute more than once;
  the system remains correct under replays.
- **Non-blocking API:** Client-facing operations return quickly and do not
  block on long-running decomposition or validation.
- **Auditability:** Every state transition and emitted output is attributable
  to an actor or process and is timestamped.

Non-guarantees (explicit):
- **No exactly-once execution:** The system does not guarantee exactly-once
  worker execution; correctness relies on idempotency.
- **No global ordering:** The system does not guarantee ordering across
  independent claims or across different operations.
- **No synchronous finality:** A successful `CreateClaim` does not imply
  decomposition, validation, or verdict completion.
- **No single source of truth:** MIC stores verifiable references and structured
  outputs; it does not replace upstream authorities.

## Operations (v0.1)

Each operation is defined as a typed method (RPC-style) with an equivalent REST mapping.

### CreateClaim

### EnqueueDecomposition (orchestrator operation)

Purpose: Schedule a Claim for asynchronous decomposition by transitioning
`Claim.decomposition_status` to `queued`.

This operation is intended for internal orchestrators (not end users).

Idempotency: MUST be idempotent. Calling EnqueueDecomposition multiple times
for the same `claim_id` MUST NOT create duplicate scheduled work.

#### Request
- `claim_id` (string, required)
- `reason` (string, optional) — e.g., `initial`, `retry`, `lease_timeout`

#### Preconditions
- Claim exists.
- Claim is not in terminal success (`decomposed`).
- If Claim is `in_progress`, EnqueueDecomposition SHOULD be a no-op to avoid
  duplicate concurrent work.

#### State transition
- `pending` -> `queued`
- `failed` -> `queued` (retry path)
- `queued` -> `queued` (idempotent no-op)

#### Response
- `claim_id` (string, required)
- `decomposition_status` (enum, required) — `queued` OR current unchanged state
- `enqueued_at` (timestamp, required)

#### Notes
- EnqueueDecomposition defines intent to process; it does not guarantee
  immediate execution.
- Actual execution is performed by DecomposeClaim workers under at-least-once semantics.

### DecomposeClaim (worker operation)

Purpose: Decompose a Claim into normalized TruthBits as an asynchronous background step.
This operation is intended for trusted internal workers (not end users).

Idempotency: MUST be idempotent. Re-running DecomposeClaim for the same `claim_id`
MUST NOT create duplicate TruthBits or contradictory linkages.

#### Request
- `claim_id` (string, required)
- `lease_token` (string, required)
- `attempt` (int, optional)

#### Preconditions
- Claim exists.
- Claim is in `queued` OR worker holds a valid lease for the claim.
- Worker MUST transition `decomposition_status` to `in_progress` atomically
  (compare-and-set) as part of lease acquisition.

#### Execution
1. Load Claim payload.
2. Decompose Claim into candidate TruthBits.
3. Persist TruthBits and their association to `claim_id`.
4. Transition `decomposition_status` to `decomposed` ONLY after outputs are persisted.

On failure:
- Record failure reason.
- Transition `decomposition_status` to `failed`.
- Retrying is performed by re-enqueueing per policy (outside this operation).

#### Response
- `claim_id` (string, required)
- `decomposition_status` (enum, required) — `decomposed` OR `failed`
- `truthbit_ids` (array[string], optional) — present on success
- `failed_reason` (string, optional) — present on failure
- `completed_at` (timestamp, required)

#### Notes
- Workers operate under at-least-once semantics; duplicate execution is expected.
- Output writes MUST be deduplicated (e.g., stable TruthBit identifiers).
- If a lease expires mid-run, the system MAY re-queue the claim; workers MUST tolerate safe reprocessing.

---
### End-to-End Execution Example (Non-normative)

This example illustrates a typical asynchronous lifecycle for a Claim.
It is descriptive only and does not introduce additional guarantees.

1. **CreateClaim**
   - A client submits a claim via `CreateClaim`.
   - The system persists the claim with:
     - `decomposition_status = pending`

2. **EnqueueDecomposition**
   - An internal orchestrator calls `EnqueueDecomposition`.
   - The claim transitions:
     - `pending → queued`
   - The claim is now eligible for background processing.

3. **DecomposeClaim (worker execution)**
   - A background worker acquires a lease on the claim.
   - The worker transitions:
     - `queued → in_progress`
   - The worker decomposes the claim into TruthBits.
   - TruthBits are persisted and linked to the claim.
   - On success, the claim transitions:
     - `in_progress → decomposed`

4. **Failure and retry (optional path)**
   - If decomposition fails, the worker transitions:
     - `in_progress → failed`
   - A subsequent call to `EnqueueDecomposition` MAY re-queue the claim:
     - `failed → queued`
   - Workers MUST tolerate reprocessing under at-least-once semantics.


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
