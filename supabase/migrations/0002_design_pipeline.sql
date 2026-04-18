-- Add tables and columns for the task-conditioned robot design pipeline.

CREATE TABLE IF NOT EXISTS designs (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ingest_job_id      TEXT NOT NULL REFERENCES ingest_jobs(id) ON DELETE CASCADE,
  candidate_id       TEXT NOT NULL CHECK (candidate_id IN ('A', 'B', 'C')),
  design_json        JSONB NOT NULL,
  bom_json           JSONB,
  is_model_preferred BOOLEAN NOT NULL DEFAULT FALSE,
  is_user_selected   BOOLEAN NOT NULL DEFAULT FALSE,
  screening_score    DOUBLE PRECISION,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_designs_ingest_candidate
  ON designs(ingest_job_id, candidate_id);

CREATE INDEX IF NOT EXISTS idx_designs_ingest_job_id
  ON designs(ingest_job_id);

CREATE INDEX IF NOT EXISTS idx_designs_model_preferred
  ON designs(ingest_job_id, is_model_preferred)
  WHERE is_model_preferred = TRUE;

ALTER TABLE evolutions
ADD COLUMN IF NOT EXISTS design_id UUID REFERENCES designs(id);

CREATE INDEX IF NOT EXISTS idx_evolutions_design_id
  ON evolutions(design_id);
