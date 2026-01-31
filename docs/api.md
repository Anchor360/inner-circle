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
### TruthBit

Represents a minimal, independently verifiable unit derived from a Claim.

Fields:
- `id` (string, immutable): globally unique identifier
- `claim_id` (string): identifier of the parent Claim
- `key` (string): semantic key describing what is being verified (e.g., filing_date, legal_name)
- `expected_type` (string): expected value type (e.g., string, date, number)
- `policy` (string): domain-specific verification ruleset identifier
- `created_at` (timestamp): when the truth bit was created
