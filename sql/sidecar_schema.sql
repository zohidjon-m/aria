CREATE TABLE IF NOT EXISTS agent_runs (
    run_id TEXT PRIMARY KEY,
    agent_name TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    status TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    output_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_items (
    evidence_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    PRIMARY KEY (run_id, evidence_id),
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

CREATE TABLE IF NOT EXISTS validation_reports (
    validation_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    status TEXT NOT NULL,
    unsupported_count INTEGER NOT NULL,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

CREATE TABLE IF NOT EXISTS recommendations (
    recommendation_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    alert_id INTEGER NOT NULL,
    customer_id INTEGER,
    disposition TEXT NOT NULL,
    confidence REAL NOT NULL,
    score REAL NOT NULL,
    reasoning_json TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed',
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

CREATE TABLE IF NOT EXISTS risk_scores (
    risk_score_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    customer_id INTEGER NOT NULL,
    score REAL NOT NULL,
    level TEXT NOT NULL,
    rationale_json TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed',
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

CREATE TABLE IF NOT EXISTS sar_drafts (
    sar_draft_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    case_id INTEGER NOT NULL,
    narrative TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft_for_human_review',
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

CREATE TABLE IF NOT EXISTS human_decisions (
    decision_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    officer_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    rationale TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

CREATE TABLE IF NOT EXISTS runtime_versions (
    run_id TEXT PRIMARY KEY,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    planner_type TEXT NOT NULL,
    model_id TEXT,
    prompt_version TEXT NOT NULL,
    tool_registry_version TEXT NOT NULL,
    runtime_bounds_json TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

CREATE TABLE IF NOT EXISTS typology_routes (
    route_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    activated_json TEXT NOT NULL,
    skipped_json TEXT NOT NULL,
    reasons_json TEXT NOT NULL,
    allowed_tools_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

CREATE TABLE IF NOT EXISTS agent_steps (
    step_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    status TEXT NOT NULL,
    thought TEXT,
    hypothesis TEXT,
    tool_name TEXT,
    stop_reason TEXT,
    error TEXT,
    step_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

CREATE TABLE IF NOT EXISTS tool_calls (
    tool_call_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    step_number INTEGER,
    tool_name TEXT NOT NULL,
    tool_args_json TEXT NOT NULL,
    status TEXT NOT NULL,
    stop_reason TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

CREATE TABLE IF NOT EXISTS observations (
    observation_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    step_number INTEGER,
    tool_name TEXT NOT NULL,
    facts_json TEXT NOT NULL,
    computed_features_json TEXT NOT NULL,
    source_refs_json TEXT NOT NULL,
    data_completeness_json TEXT NOT NULL,
    limitations_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

CREATE TABLE IF NOT EXISTS hypotheses (
    hypothesis_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    hypothesis TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

CREATE TABLE IF NOT EXISTS baseline_snapshots (
    baseline_snapshot_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    step_number INTEGER,
    baseline_assessment TEXT,
    features_json TEXT NOT NULL,
    data_completeness_json TEXT NOT NULL,
    limitations_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

CREATE TABLE IF NOT EXISTS money_flow_paths (
    money_flow_path_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    step_number INTEGER,
    path_index INTEGER NOT NULL,
    hop_count INTEGER,
    account_path_json TEXT NOT NULL,
    path_json TEXT NOT NULL,
    graph_signals_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_runtime_versions_idempotency_key
    ON runtime_versions(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_runtime_versions_subject
    ON runtime_versions(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_typology_routes_run_id
    ON typology_routes(run_id);
CREATE INDEX IF NOT EXISTS idx_agent_steps_run_step
    ON agent_steps(run_id, step_number);
CREATE INDEX IF NOT EXISTS idx_tool_calls_run_phase_tool
    ON tool_calls(run_id, phase, tool_name);
CREATE INDEX IF NOT EXISTS idx_observations_run_phase_tool
    ON observations(run_id, phase, tool_name);
CREATE INDEX IF NOT EXISTS idx_hypotheses_run_step
    ON hypotheses(run_id, step_number);
CREATE INDEX IF NOT EXISTS idx_baseline_snapshots_run_phase
    ON baseline_snapshots(run_id, phase);
CREATE INDEX IF NOT EXISTS idx_money_flow_paths_run_phase
    ON money_flow_paths(run_id, phase);
