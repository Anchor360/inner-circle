# Verification Custody Infrastructure — Core Rules

These rules govern every build decision in this repo.
They are not guidelines. They are constraints.
If a proposed change violates one of these rules, the rule wins.

---

## Rule 1 — Custody, Not Judgment

We store and expose what authoritative sources say.
We do not interpret, recommend, or decide.
The receipt asserts nothing. The compliance officer decides everything.

## Rule 2 — One Ingestion Pipeline for All Domains

Every domain must follow the same lifecycle:
Fetch -> Snapshot -> Hash -> WORM Lock -> Version -> Parse -> Serve -> Activate -> Log
No custom flows. No shortcuts. No exceptions.

## Rule 3 — Immutable Snapshots Are the Source of Truth

Serving tables are performance artifacts.
The snapshot + hash + version ID is the truth.
Replay must work even if serving tables are gone.

## Rule 4 — Policy Is Versioned, Never Hardcoded

All thresholds, matching logic, and normalization rules live in versioned policy tables.
No domain logic in application code.
If you change a threshold, you create a new policy version. You do not edit a constant.

## Rule 5 — Domains Are Connectors, Not Special Cases

Sanctions, medical, legal, scientific — all are connectors.
Core infrastructure does not change per domain.
Differentiation happens in connectors, not in the custody engine.
If sanctions required a core change, the design is wrong.

## Rule 6 — Explicit Version Activation

Only one active version per domain at any time.
Activation occurs only after snapshot lock is verified and serving table swap is complete.
Never implicit. Never 'latest row wins'. Never activate before lock is confirmed.

## Rule 7 — Deterministic Replay Is Mandatory

Given: domain + version_id + policy_version + input
The system must reproduce the same result. Always. Without exception.
If replay is not possible, the ingestion is not complete.

## Rule 8 — Governance Is Centralized

Retention periods, freshness thresholds, and activation gating are defined
in versioned system policy. Not per-tenant ad hoc logic. Not hardcoded constants.
One place. Versioned. Auditable.

## Rule 9 — No Cross-Domain Coupling

One domain's ingestion or failure cannot impact another domain's lifecycle.
OFAC failing does not affect BIS. BIS failing does not affect OFAC.
Each domain is fully isolated end to end.

## Rule 10 — The Core Must Stay Boring

Deterministic. Procedural. Policy-driven.
No cleverness in the custody engine. No magic. No shortcuts.
Differentiation happens in connectors, not in the core.
If it is interesting, it probably does not belong in the core.

---

## What These Rules Mean in Practice

- Never say 'sanctioned' or 'not sanctioned'. Say 'found on OFAC SDN list
  as of [timestamp] against version ID [X]'.
- Never score risk. Never recommend action. Never resolve conflicts between sources.
- Return the literal government source record. Not an interpretation of it.
- If WORM lock cannot be verified, the ingestion does not activate.
- If two sources disagree, report both findings. Let the customer decide.
- The serving table is always rebuilt from the snapshot. Never the other way around.

---

## The One-Sentence Positioning

We tell you what the government says, exactly when they said it,
and we prove we checked. What you do with that is your call.

---

*Last updated: 2026-02-23*
