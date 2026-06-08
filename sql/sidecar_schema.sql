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
