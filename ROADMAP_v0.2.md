# MIC / Inner-Circle — Roadmap v0.2 (Planning Only)

This document outlines candidate topics for v0.2.
It is non-normative and does not modify the v0.1 specification.

---

## Validation Lifecycle (v0.2 candidates)

Topics to define:

- When a Validation is created relative to TruthBits
- Relationship between Claim, TruthBit, and Validation
- Validator roles (human, automated, authority-backed)
- Validation idempotency and replay safety
- Partial validation and incremental evidence
- Validation failure vs abstention semantics
- Time-bounded or expiring validations (if any)

Open questions:
- Can a TruthBit have multiple concurrent validations?
- Are validations immutable, append-only, or revisable?
- How are conflicting validations represented?

---

## Verdict Lifecycle (v0.2 candidates)

Topics to define:

- How multiple validations aggregate into a Verdict
- Verdict states (e.g., provisional, disputed, settled)
- Handling disagreement and minority signals
- Temporal evolution of verdicts (verdicts over time)
- Impact of new evidence or late validations
- Separation between factual verdict and confidence score

Open questions:
- Are verdicts recomputed continuously or event-driven?
- Can verdicts be invalidated or only superseded?
- How are verdict changes audited and explained?
