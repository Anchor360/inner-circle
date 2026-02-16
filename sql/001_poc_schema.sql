-- MIC / Inner-Circle POC schema (v0.2-aligned)

CREATE TABLE IF NOT EXISTS claims (
  claim_id     TEXT PRIMARY KEY,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  content      TEXT NOT NULL,
  decomposition_status TEXT
);

CREATE TABLE IF NOT EXISTS validations (
  validation_id TEXT PRIMARY KEY,
  claim_id      TEXT NOT NULL REFERENCES claims(claim_id) ON DELETE CASCADE,
  outcome       TEXT NOT NULL CHECK (outcome IN ('supports','refutes','inconclusive')),
  confidence    DOUBLE PRECISION NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_validations_claim_created
  ON validations (claim_id, created_at DESC);

CREATE TABLE IF NOT EXISTS verdicts (
  verdict_id    TEXT PRIMARY KEY,
  claim_id      TEXT NOT NULL REFERENCES claims(claim_id) ON DELETE CASCADE,
  status        TEXT NOT NULL CHECK (status IN ('verified','disputed','indeterminate')),
  confidence    DOUBLE PRECISION NOT NULL CHECK (confidence >= 0.0 AND confidence <= 1.0),
  validation_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_verdicts_claim_created
  ON verdicts (claim_id, created_at DESC);
