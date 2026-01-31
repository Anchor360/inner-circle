# MIC / Inner-Circle — Architecture (v0.1)

## Purpose
MIC provides a verification workflow for claims. It does not replace authorities or sources. It preserves:
- what was claimed
- what evidence supports (or contradicts) it
- who validated it
- when it changed
- how it held up under dispute

This repo is intentionally early-stage: focus is clarity and reproducibility over feature breadth.

## Core concepts

### Claim
A user-submitted statement about the world.
- claim text (natural language or structured)
- domain (e.g., organization filings, memorial plaques, case law metadata)
- scope (time-bound? location-bound? versioned?)
- decomposition rule (how claim becomes Truth Bits)

### Truth Bit
A minimal, independently verifiable unit extracted from a claim.
Examples:
- entity legal name equals X
- filing date equals YYYY-MM-DD
- plaque dedication date equals YYYY-MM-DD

### Evidence
A pointer to supporting or refuting material with provenance.
Evidence types:
- primary artifact (official registry page, scanned PDF, photo of physical object)
- secondary artifact (used carefully; never authoritative alone)
- validator capture (photos/video, notes, metadata)

Provenance requirements (v0.1):
- evidence includes source type, source location, capture timestamp
- reproducible by another person

### Validation (human-in-the-loop)
Validators confirm Truth Bits against evidence and submit:
- evidence references
- extracted values
- notes + conflicts

### Verdict
A computed state for a Claim or Truth Bit derived from validations over time.
States: unverified, supported, contested, refuted, stale

## Flow (v0.1)
``` mermaid
flowchart LR
    A[Claim Ingested] --> B[Decompose into Truth Bits]
    B --> C[Assign Truth Bits for Validation]
    C --> D[Collect Evidence & Extract Values]
    D --> E[Compute Verdicts]
    E --> F[Persist History (Append-Only)]
    F --> G[Dispute / Re-Validation]
    G --> E
```
1. ingest claim
2. decompose -> truth bits
3. assign bits to validators
4. collect evidence + extracted values
5. compute verdicts
6. persist history (append-only)
7. dispute + re-validation

## Data model (conceptual)
- Claim: id, domain, text, created_at, created_by
- TruthBit: id, claim_id, key, expected_type, policy, created_at
- Evidence: id, type, uri/location, captured_at, metadata
- Validation: id, truthbit_id, validator_id, evidence_ids[], extracted_value, notes, created_at
- Verdict: id, subject_type(claim|truthbit), subject_id, status, rationale, computed_at

## Design principles
- history-first (no overwrites)
- dispute-aware (conflicts preserved)
- domain policies are explicit
- minimalism (services only when demanded)

## Non-goals (v0.1)
- tokenomics / incentives
- full identity/authz
- scaling/performance
- broad domain coverage
- automated truth (humans decide)

## Future infra direction (deferred)
Once domain + policies are stable:
- storage: Postgres (claims/bits/validations), object storage (artifacts)
- optional: event stream + search index
- API: thin service layer over the model
