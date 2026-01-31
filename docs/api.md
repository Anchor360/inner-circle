# MIC / Inner-Circle — API Contract (v0.1)
## Principles (v0.1)

- **Append-only**: no destructive updates; all changes create new records
- **Dispute-aware**: conflicting evidence and validations are preserved
- **Idempotent writes**: clients must supply idempotency keys for create operations
- **Versioned contracts**: breaking changes require a new major version
- **Human-in-the-loop**: automated assistance may exist, but verdicts derive from human validations

## Core Types (v0.1)
### Claim

Represents a user-submitted statement about the world.

Fields:
- `id` (string, immutable): globally unique identifier
- `domain` (string): domain policy namespace (e.g., organization_filings, memorials)
- `text` (string): human-readable claim statement
- `created_at` (timestamp): when the claim was created
- `created_by` (string): submitter identifier (opaque in v0.1)
- `decomposition_status` (string): decomposition state (pending, in_progress, complete, failed)
#### Decomposition lifecycle (v0.1)

The `decomposition_status` field represents the readiness of a Claim for validation.

Allowed states:
- `pending`: claim accepted, decomposition not yet started
- `in_progress`: truth-bit extraction underway
- `complete`: truth bits finalized and available for validation
- `failed`: decomposition failed and requires retry or manual intervention

Allowed transitions:
- `pending` → `in_progress`
- `in_progress` → `complete`
- `in_progress` → `failed`
- `failed` → `in_progress` (retry)

Notes:
- Transitions are append-only and recorded as events
- Clients must treat this field as **eventually consistent**
- Verdict computation MUST NOT occur until status = `complete`
### TruthBit

Represents a minimal, independently verifiable unit derived from a Claim.

Fields:
- `id` (string, immutable): globally unique identifier
- `claim_id` (string): identifier of the parent Claim
- `key` (string): semantic key describing what is being verified (e.g., filing_date, legal_name)
- `expected_type` (string): expected value type (e.g., string, date, number)
- `policy` (string): domain-specific verification ruleset identifier
- `created_at` (timestamp): when the truth bit was created
### Evidence

Represents a piece of supporting or refuting material with provenance.

Fields:
- `id` (string, immutable): globally unique identifier
- `type` (string): evidence type (primary_artifact, secondary_artifact, validator_capture)
- `uri` (string): location or reference to the evidence
- `captured_at` (timestamp): when the evidence was captured or observed
- `metadata` (map<string, string>): auxiliary provenance metadata
### Validation

Represents a human validator’s assessment of a TruthBit using one or more Evidence items.

Fields:
- `id` (string, immutable): globally unique identifier
- `truthbit_id` (string): identifier of the TruthBit being validated
- `evidence_ids` (list<string>): identifiers of Evidence used in this validation
- `extracted_value` (string): value extracted or observed by the validator
- `notes` (string): optional validator notes or rationale
- `created_at` (timestamp): when the validation was submitted
- `created_by` (string): validator identifier (opaque in v0.1)
### Verdict

Represents the computed state of a Claim or TruthBit based on accumulated validations.

Fields:
- `id` (string, immutable): globally unique identifier
- `subject_type` (string): target type (claim | truthbit)
- `subject_id` (string): identifier of the Claim or TruthBit
- `status` (string): computed state (unverified, supported, contested, refuted, stale)
- `rationale` (string): explanation of how the verdict was derived
- `computed_at` (timestamp): when the verdict was computed
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
