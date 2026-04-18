-- Add new tables for autoresearch loop.

CREATE TABLE IF NOT EXISTS evolutions (
  id              TEXT PRIMARY KEY,
  run_id          TEXT,
  program_md      TEXT,
  status          TEXT NOT NULL DEFAULT 'pending',
  best_iteration_id TEXT,
  total_cost_usd  NUMERIC(8,4) DEFAULT 0,
  started_at      TIMESTAMPTZ,
  completed_at    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS morphologies (
  id              TEXT PRIMARY KEY,
  urdf_url        TEXT,
  latent_z_json   TEXT,
  params_json     TEXT,
  num_dof         INT,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS iterations (
  id                  TEXT PRIMARY KEY,
  evolution_id        TEXT REFERENCES evolutions(id),
  iter_num            INT NOT NULL,
  morphology_id       TEXT REFERENCES morphologies(id),
  controller_ckpt_url TEXT,
  trajectory_npz_url  TEXT,
  replay_mp4_url      TEXT,
  fitness_score       NUMERIC(6,4),
  tracking_error      NUMERIC(6,4),
  er16_success_prob   NUMERIC(6,4),
  reasoning_log       TEXT,
  train_py_diff       TEXT,
  morph_factory_diff  TEXT,
  created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ingest_jobs (
  id              TEXT PRIMARY KEY,
  source_url      TEXT,
  er16_plan_json  TEXT,
  gvhmr_job_id    TEXT,
  smpl_path       TEXT,
  status          TEXT NOT NULL DEFAULT 'pending',
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS program_md_drafts (
  id                  TEXT PRIMARY KEY,
  evolution_id        TEXT REFERENCES evolutions(id),
  generator           TEXT,
  draft_content       TEXT,
  approved            BOOLEAN DEFAULT FALSE,
  approved_at         TIMESTAMPTZ,
  user_edited_content TEXT
);

-- Indexes on high-traffic FK columns
CREATE INDEX IF NOT EXISTS idx_iterations_evolution_id ON iterations(evolution_id);
CREATE INDEX IF NOT EXISTS idx_iterations_morphology_id ON iterations(morphology_id);
CREATE INDEX IF NOT EXISTS idx_program_md_drafts_evolution_id ON program_md_drafts(evolution_id);
CREATE INDEX IF NOT EXISTS idx_evolutions_run_id ON evolutions(run_id);

-- Enable Supabase Realtime on iterations so dashboard updates live
ALTER PUBLICATION supabase_realtime ADD TABLE iterations;
