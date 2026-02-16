-- 002_sources.sql
-- Adds a normalized source registry + ties validations to sources

BEGIN;

-- 1) Create sources table
CREATE TABLE IF NOT EXISTS sources (
  source_id UUID PRIMARY KEY,
  source_name TEXT NOT NULL,
  source_type TEXT NOT NULL,
  authority_tier TEXT NOT NULL,
  source_uri TEXT,
  source_published_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  CONSTRAINT sources_authority_tier_check
    CHECK (authority_tier IN ('primary','secondary','tertiary','unclassified'))
);

-- 2) Insert one default Unclassified source (fixed UUID so we can backfill deterministically)
INSERT INTO sources (
  source_id, source_name, source_type, authority_tier, source_uri
)
VALUES (
  '00000000-0000-0000-0000-000000000001',
  'Unclassified',
  'unclassified',
  'unclassified',
  NULL
)
ON CONFLICT (source_id) DO NOTHING;

-- 3) Add source_id column to validations (nullable for the moment)
ALTER TABLE validations
  ADD COLUMN IF NOT EXISTS source_id UUID;

-- 4) Backfill any existing validations to Unclassified
UPDATE validations
SET source_id = '00000000-0000-0000-0000-000000000001'
WHERE source_id IS NULL;

-- 5) Enforce FK + NOT NULL now that backfill is done
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'validations_source_id_fkey'
  ) THEN
    ALTER TABLE validations
      ADD CONSTRAINT validations_source_id_fkey
      FOREIGN KEY (source_id) REFERENCES sources(source_id);
  END IF;
END $$;

ALTER TABLE validations
  ALTER COLUMN source_id SET NOT NULL;

-- 6) Helpful index for common queries
CREATE INDEX IF NOT EXISTS idx_validations_source_id ON validations(source_id);

COMMIT;
