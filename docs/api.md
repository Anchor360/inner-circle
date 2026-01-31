# MIC / Inner-Circle — API Contract (v0.1)
## Principles (v0.1)

- **Append-only**: no destructive updates; all changes create new records
- **Dispute-aware**: conflicting evidence and validations are preserved
- **Idempotent writes**: clients must supply idempotency keys for create operations
- **Versioned contracts**: breaking changes require a new major version
- **Human-in-the-loop**: automated assistance may exist, but verdicts derive from human validations

