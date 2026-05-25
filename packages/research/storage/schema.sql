CREATE TABLE IF NOT EXISTS experiments (
    experiment_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    prompt TEXT NOT NULL,
    prompt_label TEXT,
    config_json TEXT NOT NULL,
    repro_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error TEXT,
    langsmith_trace_id TEXT,
    langfuse_trace_id TEXT,
    debug_json TEXT,
    FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id)
);

CREATE TABLE IF NOT EXISTS designs (
    design_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    design_name TEXT NOT NULL,
    ir_json TEXT NOT NULL,
    mjcf_xml TEXT,
    metrics_json TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS run_metrics (
    run_id TEXT PRIMARY KEY,
    report_json TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(run_id)
);

CREATE TABLE IF NOT EXISTS test_prompts (
    prompt_id TEXT PRIMARY KEY,
    prompt TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    expected_robo_grammar_json TEXT,
    created_at TEXT NOT NULL
);
