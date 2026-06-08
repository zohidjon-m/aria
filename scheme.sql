
-- SECTION 1: REFERENCE / LOOKUP TABLES


-- Countries with FATF risk ratings
CREATE TABLE countries (
                           country_code      CHAR(2) PRIMARY KEY,
                           country_name      VARCHAR(100) NOT NULL UNIQUE,
                           fatf_status       VARCHAR(20) NOT NULL DEFAULT 'whitelist'
                               CHECK (fatf_status IN ('blacklist', 'greylist', 'whitelist')),
                           risk_score        DECIMAL(4,2) NOT NULL DEFAULT 0.0
                               CHECK (risk_score BETWEEN 0 AND 10),
                           is_sanctioned     BOOLEAN DEFAULT FALSE,
                           updated_at        TIMESTAMP DEFAULT NOW()
);

-- Officer roles for RBAC
CREATE TABLE officer_roles (
                               role_id           SERIAL PRIMARY KEY,
                               role_name         VARCHAR(50) NOT NULL UNIQUE,
                               can_view_alerts   BOOLEAN DEFAULT TRUE,
                               can_manage_cases  BOOLEAN DEFAULT FALSE,
                               can_file_sar      BOOLEAN DEFAULT FALSE,
                               can_manage_rules  BOOLEAN DEFAULT FALSE,
                               can_manage_users  BOOLEAN DEFAULT FALSE,
                               description       TEXT
);

-- Currency exchange rates (daily snapshots)
CREATE TABLE currency_rates (
                                rate_id           SERIAL PRIMARY KEY,
                                currency_code     CHAR(3) NOT NULL,
                                currency_name     VARCHAR(50) NOT NULL,
                                rate_to_usd       DECIMAL(18,6) NOT NULL CHECK (rate_to_usd > 0),
                                rate_date         DATE NOT NULL DEFAULT CURRENT_DATE,
                                UNIQUE (currency_code, rate_date)
);


-- SECTION 2: CORE BANKING TABLES


-- Bank branches
CREATE TABLE branches (
                          branch_id         SERIAL PRIMARY KEY,
                          branch_name       VARCHAR(100) NOT NULL,
                          city              VARCHAR(100) NOT NULL,
                          country_code      CHAR(2) NOT NULL REFERENCES countries(country_code),
                          address           TEXT,
                          phone             VARCHAR(20),
                          is_active         BOOLEAN DEFAULT TRUE,
                          opened_at         DATE NOT NULL DEFAULT CURRENT_DATE
);

-- Compliance officers
CREATE TABLE compliance_officers (
                                     officer_id        SERIAL PRIMARY KEY,
                                     role_id           INT NOT NULL REFERENCES officer_roles(role_id),
                                     branch_id         INT REFERENCES branches(branch_id),
                                     full_name         VARCHAR(100) NOT NULL,
                                     email             VARCHAR(150) NOT NULL UNIQUE,
                                     phone             VARCHAR(20),
                                     is_active         BOOLEAN DEFAULT TRUE,
                                     hired_at          DATE NOT NULL DEFAULT CURRENT_DATE,
                                     last_login        TIMESTAMP
);

-- Add manager FK to branches after officers table exists
ALTER TABLE branches ADD COLUMN manager_id INT REFERENCES compliance_officers(officer_id);

-- Customers
CREATE TABLE customers (
                           customer_id       SERIAL PRIMARY KEY,
                           full_name         VARCHAR(150) NOT NULL,
                           email             VARCHAR(150) NOT NULL UNIQUE,
                           phone             VARCHAR(20),
                           nationality       CHAR(2) REFERENCES countries(country_code),
                           date_of_birth     DATE,
                           occupation        VARCHAR(100),
                           risk_level        VARCHAR(10) NOT NULL DEFAULT 'low'
                               CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
                           kyc_status        VARCHAR(20) NOT NULL DEFAULT 'pending'
                               CHECK (kyc_status IN ('pending', 'verified', 'rejected', 'expired')),
                           is_active         BOOLEAN DEFAULT TRUE,
                           created_at        TIMESTAMP DEFAULT NOW(),
                           updated_at        TIMESTAMP DEFAULT NOW()
);

-- Bank accounts
CREATE TABLE accounts (
                          account_id        SERIAL PRIMARY KEY,
                          customer_id       INT NOT NULL REFERENCES customers(customer_id),
                          branch_id         INT NOT NULL REFERENCES branches(branch_id),
                          account_number    VARCHAR(20) NOT NULL UNIQUE,
                          account_type      VARCHAR(20) NOT NULL
                              CHECK (account_type IN ('checking', 'savings', 'business', 'investment')),
                          currency_code     CHAR(3) NOT NULL DEFAULT 'USD',
                          balance           DECIMAL(18,2) NOT NULL DEFAULT 0.00 CHECK (balance >= 0),
                          status            VARCHAR(20) NOT NULL DEFAULT 'active'
                              CHECK (status IN ('active', 'frozen', 'closed', 'suspended')),
                          opened_at         TIMESTAMP DEFAULT NOW(),
                          closed_at         TIMESTAMP
);

-- Transactions
CREATE TABLE transactions (
                              transaction_id         SERIAL PRIMARY KEY,
                              account_id             INT NOT NULL REFERENCES accounts(account_id),
                              counterparty_account_id INT REFERENCES accounts(account_id),
                              transaction_type       VARCHAR(30) NOT NULL
                                  CHECK (transaction_type IN (
                                                              'deposit', 'withdrawal', 'transfer_domestic',
                                                              'transfer_international', 'wire', 'cash'
                                      )),
                              amount                 DECIMAL(18,2) NOT NULL CHECK (amount > 0),
                              amount_usd             DECIMAL(18,2),
                              currency_code          CHAR(3) NOT NULL DEFAULT 'USD',
                              destination_country    CHAR(2) REFERENCES countries(country_code),
                              description            TEXT,
                              reference_number       VARCHAR(50) UNIQUE,
                              status                 VARCHAR(20) NOT NULL DEFAULT 'completed'
                                  CHECK (status IN ('pending', 'completed', 'failed', 'reversed')),
                              is_flagged             BOOLEAN DEFAULT FALSE,
                              created_at             TIMESTAMP DEFAULT NOW()
);


-- SECTION 3: COMPLIANCE ENGINE TABLES

-- Compliance rules (the rulebook)
CREATE TABLE compliance_rules (
                                  rule_id           SERIAL PRIMARY KEY,
                                  rule_name         VARCHAR(100) NOT NULL UNIQUE,
                                  rule_type         VARCHAR(30) NOT NULL
                                      CHECK (rule_type IN (
                                                           'threshold', 'frequency', 'geography',
                                                           'structuring', 'velocity', 'sanctions'
                                          )),
                                  threshold_amount  DECIMAL(18,2),
                                  max_frequency     INT,
                                  time_window_days  INT,
                                  applies_to        VARCHAR(20) DEFAULT 'all'
                                      CHECK (applies_to IN ('all', 'international', 'domestic', 'cash')),
                                  severity          VARCHAR(10) NOT NULL DEFAULT 'medium'
                                      CHECK (severity IN ('low', 'medium', 'high', 'critical')),
                                  is_active         BOOLEAN DEFAULT TRUE,
                                  created_at        TIMESTAMP DEFAULT NOW()
);

-- Alerts (auto-generated by triggers)
CREATE TABLE alerts (
                        alert_id          SERIAL PRIMARY KEY,
                        transaction_id    INT NOT NULL REFERENCES transactions(transaction_id),
                        rule_id           INT NOT NULL REFERENCES compliance_rules(rule_id),
                        assigned_to       INT REFERENCES compliance_officers(officer_id),
                        severity          VARCHAR(10) NOT NULL
                            CHECK (severity IN ('low', 'medium', 'high', 'critical')),
                        status            VARCHAR(20) NOT NULL DEFAULT 'open'
                            CHECK (status IN ('open', 'under_review', 'escalated', 'dismissed', 'resolved')),
                        is_escalated      BOOLEAN DEFAULT FALSE,
                        created_at        TIMESTAMP DEFAULT NOW(),
                        resolved_at       TIMESTAMP,
                        notes             TEXT
);

-- Alert comments (officer investigation notes)
CREATE TABLE alert_comments (
                                comment_id        SERIAL PRIMARY KEY,
                                alert_id          INT NOT NULL REFERENCES alerts(alert_id),
                                officer_id        INT NOT NULL REFERENCES compliance_officers(officer_id),
                                comment           TEXT NOT NULL,
                                created_at        TIMESTAMP DEFAULT NOW()
);

-- Cases (full investigations)
CREATE TABLE cases (
                       case_id           SERIAL PRIMARY KEY,
                       customer_id       INT NOT NULL REFERENCES customers(customer_id),
                       officer_id        INT NOT NULL REFERENCES compliance_officers(officer_id),
                       case_type         VARCHAR(20) NOT NULL
                           CHECK (case_type IN ('AML', 'fraud', 'KYC', 'sanctions', 'structuring')),
                       status            VARCHAR(20) NOT NULL DEFAULT 'open'
                           CHECK (status IN (
                                             'open', 'under_review', 'escalated',
                                             'closed_clean', 'closed_sar'
                               )),
                       priority          VARCHAR(10) NOT NULL DEFAULT 'medium'
                           CHECK (priority IN ('low', 'medium', 'high', 'critical')),
                       opened_at         TIMESTAMP DEFAULT NOW(),
                       closed_at         TIMESTAMP,
                       summary           TEXT,
                       resolution        TEXT
);

-- Case-Alert junction (M:N)
CREATE TABLE case_alerts (
                             case_id           INT NOT NULL REFERENCES cases(case_id),
                             alert_id          INT NOT NULL REFERENCES alerts(alert_id),
                             added_at          TIMESTAMP DEFAULT NOW(),
                             added_by          INT REFERENCES compliance_officers(officer_id),
                             PRIMARY KEY (case_id, alert_id)
);

-- Risk scores history per customer
CREATE TABLE risk_scores (
                             score_id          SERIAL PRIMARY KEY,
                             customer_id       INT NOT NULL REFERENCES customers(customer_id),
                             score             DECIMAL(5,2) NOT NULL CHECK (score BETWEEN 0 AND 100),
                             score_level       VARCHAR(10) NOT NULL
                                 CHECK (score_level IN ('low', 'medium', 'high', 'critical')),
                             computed_by       VARCHAR(20) NOT NULL DEFAULT 'system'
                                 CHECK (computed_by IN ('system', 'agent', 'officer')),
                             computed_at       TIMESTAMP DEFAULT NOW(),
                             reasoning         TEXT
);

-- Regulatory reports (SARs, CTRs)
CREATE TABLE regulatory_reports (
                                    report_id         SERIAL PRIMARY KEY,
                                    case_id           INT NOT NULL REFERENCES cases(case_id),
                                    officer_id        INT NOT NULL REFERENCES compliance_officers(officer_id),
                                    report_type       VARCHAR(10) NOT NULL
                                        CHECK (report_type IN ('SAR', 'CTR', 'STR')),
                                    regulator         VARCHAR(100) NOT NULL,
                                    status            VARCHAR(20) NOT NULL DEFAULT 'draft'
                                        CHECK (status IN ('draft', 'submitted', 'acknowledged', 'rejected')),
                                    submitted_at      TIMESTAMP,
                                    deadline          TIMESTAMP,
                                    reference_number  VARCHAR(100) UNIQUE,
                                    created_at        TIMESTAMP DEFAULT NOW()
);

-- SECTION 4: SCREENING TABLES
-- Sanctions list
CREATE TABLE sanctions_list (
                                sanction_id       SERIAL PRIMARY KEY,
                                full_name         VARCHAR(200) NOT NULL,
                                entity_type       VARCHAR(20) NOT NULL
                                    CHECK (entity_type IN ('individual', 'organization', 'vessel', 'aircraft')),
                                country_code      CHAR(2) REFERENCES countries(country_code),
                                sanction_type     VARCHAR(50),
                                listed_by         VARCHAR(100) NOT NULL,
                                listed_at         DATE NOT NULL,
                                is_active         BOOLEAN DEFAULT TRUE,
                                notes             TEXT
);

-- PEP (Politically Exposed Persons) list
CREATE TABLE pep_list (
                          pep_id            SERIAL PRIMARY KEY,
                          full_name         VARCHAR(200) NOT NULL,
                          position          VARCHAR(200) NOT NULL,
                          country_code      CHAR(2) REFERENCES countries(country_code),
                          pep_level         VARCHAR(20) NOT NULL
                              CHECK (pep_level IN ('domestic', 'foreign', 'international')),
                          is_active         BOOLEAN DEFAULT TRUE,
                          since_date        DATE,
                          notes             TEXT
);

-- SECTION 5: ANALYTICS TABLES
-- Aggregated behavioral patterns per customer
CREATE TABLE transaction_patterns (
                                      pattern_id        SERIAL PRIMARY KEY,
                                      customer_id       INT NOT NULL REFERENCES customers(customer_id),
                                      avg_transaction   DECIMAL(18,2),
                                      max_transaction   DECIMAL(18,2),
                                      monthly_volume    DECIMAL(18,2),
                                      typical_countries TEXT,
                                      international_pct DECIMAL(5,2),
                                      cash_pct          DECIMAL(5,2),
                                      computed_at       TIMESTAMP DEFAULT NOW()
);

-- Monthly compliance summary per branch
CREATE TABLE monthly_reports (
                                 report_id         SERIAL PRIMARY KEY,
                                 branch_id         INT NOT NULL REFERENCES branches(branch_id),
                                 report_month      DATE NOT NULL,
                                 total_transactions  INT DEFAULT 0,
                                 total_volume_usd    DECIMAL(18,2) DEFAULT 0,
                                 total_alerts        INT DEFAULT 0,
                                 total_cases         INT DEFAULT 0,
                                 sars_filed          INT DEFAULT 0,
                                 generated_at      TIMESTAMP DEFAULT NOW(),
                                 UNIQUE (branch_id, report_month)
);

-- Audit log (every officer action)
CREATE TABLE audit_log (
                           log_id            SERIAL PRIMARY KEY,
                           officer_id        INT NOT NULL REFERENCES compliance_officers(officer_id),
                           case_id           INT REFERENCES cases(case_id),
                           alert_id          INT REFERENCES alerts(alert_id),
                           action            VARCHAR(100) NOT NULL,
                           entity_type       VARCHAR(50),
                           entity_id         INT,
                           details           TEXT,
                           ip_address        INET,
                           action_at         TIMESTAMP DEFAULT NOW()
);

-- SECTION 6: INDEXES

CREATE INDEX idx_transactions_created_at    ON transactions(created_at);
CREATE INDEX idx_transactions_account_id    ON transactions(account_id);
CREATE INDEX idx_transactions_amount        ON transactions(amount);
CREATE INDEX idx_transactions_is_flagged    ON transactions(is_flagged);
CREATE INDEX idx_transactions_dest_country  ON transactions(destination_country);
CREATE INDEX idx_alerts_status              ON alerts(status);
CREATE INDEX idx_alerts_severity            ON alerts(severity);
CREATE INDEX idx_alerts_created_at          ON alerts(created_at);
CREATE INDEX idx_customers_risk_level       ON customers(risk_level);
CREATE INDEX idx_customers_kyc_status       ON customers(kyc_status);
CREATE INDEX idx_cases_status               ON cases(status);
CREATE INDEX idx_cases_customer_id          ON cases(customer_id);
CREATE INDEX idx_risk_scores_customer_id    ON risk_scores(customer_id);
CREATE INDEX idx_audit_log_officer_id       ON audit_log(officer_id);
CREATE INDEX idx_audit_log_action_at        ON audit_log(action_at);

-- SECTION 7: VIEWS

-- High risk customer dashboard
CREATE VIEW vw_high_risk_customers AS
SELECT
    c.customer_id,
    c.full_name,
    c.risk_level,
    c.kyc_status,
    c.nationality,
    COUNT(DISTINCT a.account_id)    AS total_accounts,
    COUNT(DISTINCT t.transaction_id) AS total_transactions,
    SUM(t.amount_usd)               AS total_volume_usd,
    COUNT(DISTINCT al.alert_id)     AS total_alerts,
    COUNT(DISTINCT cs.case_id)      AS total_cases,
    rs.score                        AS latest_risk_score
FROM customers c
         LEFT JOIN accounts a        ON c.customer_id = a.customer_id
         LEFT JOIN transactions t    ON a.account_id  = t.account_id
         LEFT JOIN alerts al         ON t.transaction_id = al.transaction_id
         LEFT JOIN cases cs          ON c.customer_id = cs.customer_id
         LEFT JOIN LATERAL (
    SELECT score FROM risk_scores
    WHERE customer_id = c.customer_id
    ORDER BY computed_at DESC LIMIT 1
    ) rs ON TRUE
WHERE c.risk_level IN ('high', 'critical')
GROUP BY c.customer_id, c.full_name, c.risk_level,
         c.kyc_status, c.nationality, rs.score;

-- Officer workload dashboard
CREATE VIEW vw_officer_workload AS
SELECT
    o.officer_id,
    o.full_name,
    r.role_name,
    COUNT(DISTINCT al.alert_id)  AS open_alerts,
    COUNT(DISTINCT cs.case_id)   AS active_cases,
    MAX(al.created_at)           AS last_alert_received
FROM compliance_officers o
         LEFT JOIN officer_roles r    ON o.role_id   = r.role_id
         LEFT JOIN alerts al          ON o.officer_id = al.assigned_to
    AND al.status = 'open'
         LEFT JOIN cases cs           ON o.officer_id = cs.officer_id
    AND cs.status NOT IN ('closed_clean', 'closed_sar')
GROUP BY o.officer_id, o.full_name, r.role_name;

-- Branch compliance summary
CREATE VIEW vw_branch_compliance AS
SELECT
    b.branch_id,
    b.branch_name,
    b.city,
    co.country_name,
    COUNT(DISTINCT a.account_id)       AS total_accounts,
    COUNT(DISTINCT t.transaction_id)   AS total_transactions,
    SUM(t.amount_usd)                  AS total_volume_usd,
    COUNT(DISTINCT al.alert_id)        AS total_alerts,
    COUNT(DISTINCT cs.case_id)         AS total_cases
FROM branches b
         LEFT JOIN countries co   ON b.country_code   = co.country_code
         LEFT JOIN accounts a     ON b.branch_id      = a.branch_id
         LEFT JOIN transactions t ON a.account_id     = t.account_id
         LEFT JOIN alerts al      ON t.transaction_id = al.transaction_id
         LEFT JOIN cases cs       ON a.customer_id    = cs.customer_id
GROUP BY b.branch_id, b.branch_name, b.city, co.country_name;

-- ============================================================
-- SECTION 8: FUNCTIONS
-- ============================================================

-- Compute customer risk score
CREATE OR REPLACE FUNCTION compute_risk_score(p_customer_id INT)
    RETURNS DECIMAL(5,2) AS $$
DECLARE
    v_score         DECIMAL(5,2) := 0;
    v_alert_count   INT;
    v_case_count    INT;
    v_intl_pct      DECIMAL(5,2);
    v_risk_level    VARCHAR(10);
BEGIN
    SELECT COUNT(*) INTO v_alert_count
    FROM alerts al
             JOIN transactions t ON al.transaction_id = t.transaction_id
             JOIN accounts a ON t.account_id = a.account_id
    WHERE a.customer_id = p_customer_id;

    SELECT COUNT(*) INTO v_case_count
    FROM cases WHERE customer_id = p_customer_id;

    SELECT COALESCE(
                   SUM(CASE WHEN transaction_type = 'transfer_international' THEN 1 ELSE 0 END) * 100.0
                       / NULLIF(COUNT(*), 0), 0
           ) INTO v_intl_pct
    FROM transactions t
             JOIN accounts a ON t.account_id = a.account_id
    WHERE a.customer_id = p_customer_id;

    SELECT risk_level INTO v_risk_level
    FROM customers WHERE customer_id = p_customer_id;

    v_score := v_score + LEAST(v_alert_count * 5, 40);
    v_score := v_score + LEAST(v_case_count * 10, 30);
    v_score := v_score + LEAST(v_intl_pct * 0.2, 20);
    v_score := v_score + CASE v_risk_level
                             WHEN 'critical' THEN 10
                             WHEN 'high'     THEN 7
                             WHEN 'medium'   THEN 3
                             ELSE 0 END;

    RETURN LEAST(v_score, 100);
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- SECTION 9: STORED PROCEDURES
-- ============================================================

-- Insert new transaction and auto-check rules
CREATE OR REPLACE PROCEDURE sp_insert_transaction(
    p_account_id      INT,
    p_counterparty_id INT,
    p_type            VARCHAR,
    p_amount          DECIMAL,
    p_currency        CHAR(3),
    p_dest_country    CHAR(2),
    p_description     TEXT
)
    LANGUAGE plpgsql AS $$
DECLARE
    v_transaction_id INT;
    v_amount_usd     DECIMAL(18,2);
    v_rate           DECIMAL(18,6);
BEGIN
    SELECT rate_to_usd INTO v_rate
    FROM currency_rates
    WHERE currency_code = p_currency
    ORDER BY rate_date DESC LIMIT 1;

    v_amount_usd := p_amount * COALESCE(v_rate, 1);

    INSERT INTO transactions (
        account_id, counterparty_account_id, transaction_type,
        amount, amount_usd, currency_code,
        destination_country, description, status
    ) VALUES (
                 p_account_id, p_counterparty_id, p_type,
                 p_amount, v_amount_usd, p_currency,
                 p_dest_country, p_description, 'completed'
             ) RETURNING transaction_id INTO v_transaction_id;

    COMMIT;
END;
$$;

-- Generate monthly compliance report for a branch
CREATE OR REPLACE PROCEDURE sp_generate_monthly_report(
    p_branch_id  INT,
    p_month      DATE
)
    LANGUAGE plpgsql AS $$
DECLARE
    v_total_tx    INT;
    v_volume      DECIMAL(18,2);
    v_alerts      INT;
    v_cases       INT;
    v_sars        INT;
BEGIN
    SELECT COUNT(*), COALESCE(SUM(t.amount_usd), 0)
    INTO v_total_tx, v_volume
    FROM transactions t
             JOIN accounts a ON t.account_id = a.account_id
    WHERE a.branch_id = p_branch_id
      AND DATE_TRUNC('month', t.created_at) = DATE_TRUNC('month', p_month);

    SELECT COUNT(*) INTO v_alerts
    FROM alerts al
             JOIN transactions t ON al.transaction_id = t.transaction_id
             JOIN accounts a ON t.account_id = a.account_id
    WHERE a.branch_id = p_branch_id
      AND DATE_TRUNC('month', al.created_at) = DATE_TRUNC('month', p_month);

    SELECT COUNT(*) INTO v_cases
    FROM cases cs
             JOIN customers c ON cs.customer_id = c.customer_id
             JOIN accounts a ON c.customer_id = a.customer_id
    WHERE a.branch_id = p_branch_id
      AND DATE_TRUNC('month', cs.opened_at) = DATE_TRUNC('month', p_month);

    SELECT COUNT(*) INTO v_sars
    FROM regulatory_reports rr
             JOIN cases cs ON rr.case_id = cs.case_id
             JOIN customers c ON cs.customer_id = c.customer_id
             JOIN accounts a ON c.customer_id = a.customer_id
    WHERE a.branch_id = p_branch_id
      AND rr.report_type = 'SAR'
      AND DATE_TRUNC('month', rr.created_at) = DATE_TRUNC('month', p_month);

    INSERT INTO monthly_reports (
        branch_id, report_month, total_transactions,
        total_volume_usd, total_alerts, total_cases, sars_filed
    ) VALUES (
                 p_branch_id, DATE_TRUNC('month', p_month),
                 v_total_tx, v_volume, v_alerts, v_cases, v_sars
             )
    ON CONFLICT (branch_id, report_month) DO UPDATE SET
                                            total_transactions = EXCLUDED.total_transactions,
                                            total_volume_usd   = EXCLUDED.total_volume_usd,
                                            total_alerts       = EXCLUDED.total_alerts,
                                            total_cases        = EXCLUDED.total_cases,
                                            sars_filed         = EXCLUDED.sars_filed,
                                            generated_at       = NOW();
END;
$$;

-- ============================================================
-- SECTION 10: TRIGGERS
-- ============================================================

-- Auto-generate alert when transaction breaks compliance rules
CREATE OR REPLACE FUNCTION fn_check_compliance_rules()
    RETURNS TRIGGER AS $$
DECLARE
    v_rule       RECORD;
    v_freq_count INT;
BEGIN
    FOR v_rule IN
        SELECT * FROM compliance_rules WHERE is_active = TRUE
        LOOP
            -- Threshold rule
            IF v_rule.rule_type = 'threshold'
                AND NEW.amount_usd >= v_rule.threshold_amount THEN
                INSERT INTO alerts (transaction_id, rule_id, severity, status)
                VALUES (NEW.transaction_id, v_rule.rule_id, v_rule.severity, 'open');

                -- Geography rule
            ELSIF v_rule.rule_type = 'geography'
                AND NEW.destination_country IS NOT NULL THEN
                IF EXISTS (
                    SELECT 1 FROM countries
                    WHERE country_code = NEW.destination_country
                      AND fatf_status IN ('blacklist', 'greylist')
                ) THEN
                    INSERT INTO alerts (transaction_id, rule_id, severity, status)
                    VALUES (NEW.transaction_id, v_rule.rule_id, 'high', 'open');
                END IF;

                -- Frequency rule
            ELSIF v_rule.rule_type = 'frequency'
                AND v_rule.time_window_days IS NOT NULL THEN
                SELECT COUNT(*) INTO v_freq_count
                FROM transactions t
                WHERE t.account_id = NEW.account_id
                  AND t.created_at >= NOW() - (v_rule.time_window_days || ' days')::INTERVAL
                  AND (v_rule.applies_to = 'all'
                    OR t.transaction_type LIKE '%' || v_rule.applies_to || '%');

                IF v_freq_count >= v_rule.max_frequency THEN
                    INSERT INTO alerts (transaction_id, rule_id, severity, status)
                    VALUES (NEW.transaction_id, v_rule.rule_id, v_rule.severity, 'open');
                END IF;
            END IF;
        END LOOP;

    -- Mark transaction as flagged if any alert created
    UPDATE transactions
    SET is_flagged = TRUE
    WHERE transaction_id = NEW.transaction_id
      AND EXISTS (
        SELECT 1 FROM alerts WHERE transaction_id = NEW.transaction_id
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_compliance_check
    AFTER INSERT ON transactions
    FOR EACH ROW EXECUTE FUNCTION fn_check_compliance_rules();

-- Auto log every case status change
CREATE OR REPLACE FUNCTION fn_audit_case_changes()
    RETURNS TRIGGER AS $$
BEGIN
    IF OLD.status IS DISTINCT FROM NEW.status THEN
        INSERT INTO audit_log (officer_id, case_id, action, entity_type, entity_id, details)
        VALUES (
                   NEW.officer_id,
                   NEW.case_id,
                   'status_change',
                   'case',
                   NEW.case_id,
                   'Status changed from ' || OLD.status || ' to ' || NEW.status
               );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_audit_case
    AFTER UPDATE ON cases
    FOR EACH ROW EXECUTE FUNCTION fn_audit_case_changes();

-- ============================================================
-- SECTION 11: AUTHORIZATION
-- ============================================================

-- Create roles
CREATE ROLE junior_officer;
CREATE ROLE senior_officer;
CREATE ROLE compliance_manager;
CREATE ROLE db_admin;

-- Junior officer: read only on most tables, can comment on alerts
GRANT SELECT ON customers, accounts, transactions, alerts,
    alert_comments, cases, compliance_rules,
    countries, branches TO junior_officer;
GRANT INSERT ON alert_comments TO junior_officer;

-- Senior officer: can manage alerts and cases
GRANT SELECT, INSERT, UPDATE ON alerts, cases,
    case_alerts, risk_scores, regulatory_reports TO senior_officer;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO senior_officer;

-- Compliance manager: full access except system tables
GRANT ALL ON customers, accounts, transactions, alerts,
    cases, compliance_rules, sanctions_list,
    pep_list, regulatory_reports, monthly_reports TO compliance_manager;

-- DB admin: full access
GRANT ALL ON ALL TABLES IN SCHEMA public TO db_admin;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO db_admin;

-- ============================================================
-- SECTION 12: SAMPLE COMPLIANCE RULES
-- ============================================================

INSERT INTO compliance_rules (rule_name, rule_type, threshold_amount, max_frequency, time_window_days, applies_to, severity) VALUES
                            ('Large Cash Transaction',        'threshold',   10000.00, NULL, NULL, 'cash',          'high'),
                            ('Large Wire Transfer',           'threshold',   50000.00, NULL, NULL, 'all',           'high'),
                            ('Frequent International',        'frequency',   NULL,     5,    7,    'international', 'medium'),
                            ('High Risk Country Transfer',    'geography',   NULL,     NULL, NULL, 'international', 'critical'),
                            ('Rapid Succession Transfers',    'velocity',    NULL,     10,   1,    'all',           'high'),
                            ('Structuring Detection',         'structuring', 9000.00,  3,    1,    'all',           'critical'),
                            ('Sanctions Match',               'sanctions',   NULL,     NULL, NULL, 'all',           'critical');
-- Reference bank core schema for local demos and adapter development.
--
-- Real deployments should not run this against a bank core database. The
-- compliance sidecar reads the bank source through a read-only adapter and
-- stores generated artifacts in a separate sidecar database.

CREATE TABLE IF NOT EXISTS countries (
    country_code CHAR(2) PRIMARY KEY,
    country_name VARCHAR(100) NOT NULL,
    fatf_status VARCHAR(30) NOT NULL,
    risk_score NUMERIC(5, 2) NOT NULL DEFAULT 0,
    is_sanctioned BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS officer_roles (
    role_id INTEGER PRIMARY KEY,
    role_name VARCHAR(80) NOT NULL UNIQUE,
    can_view_alerts BOOLEAN NOT NULL DEFAULT FALSE,
    can_manage_cases BOOLEAN NOT NULL DEFAULT FALSE,
    can_file_sar BOOLEAN NOT NULL DEFAULT FALSE,
    can_manage_rules BOOLEAN NOT NULL DEFAULT FALSE,
    can_manage_users BOOLEAN NOT NULL DEFAULT FALSE,
    description TEXT
);

CREATE TABLE IF NOT EXISTS currency_rates (
    currency_code CHAR(3) NOT NULL,
    currency_name VARCHAR(80) NOT NULL,
    rate_to_usd NUMERIC(18, 8) NOT NULL,
    rate_date DATE NOT NULL,
    PRIMARY KEY (currency_code, rate_date)
);

CREATE TABLE IF NOT EXISTS branches (
    branch_id INTEGER PRIMARY KEY,
    branch_name VARCHAR(150) NOT NULL,
    city VARCHAR(100) NOT NULL,
    country_code CHAR(2) NOT NULL REFERENCES countries(country_code),
    address TEXT,
    phone VARCHAR(30),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    opened_at DATE,
    manager_id INTEGER
);

CREATE TABLE IF NOT EXISTS compliance_officers (
    officer_id INTEGER PRIMARY KEY,
    role_id INTEGER NOT NULL REFERENCES officer_roles(role_id),
    branch_id INTEGER NOT NULL REFERENCES branches(branch_id),
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    phone VARCHAR(30),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    hired_at DATE
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'branches_manager_fk'
    ) THEN
        ALTER TABLE branches
            ADD CONSTRAINT branches_manager_fk
            FOREIGN KEY (manager_id) REFERENCES compliance_officers(officer_id)
            DEFERRABLE INITIALLY DEFERRED;
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(150) UNIQUE,
    phone VARCHAR(30),
    nationality CHAR(2) REFERENCES countries(country_code),
    date_of_birth DATE,
    occupation VARCHAR(100),
    risk_level VARCHAR(30) NOT NULL DEFAULT 'low',
    kyc_status VARCHAR(30) NOT NULL DEFAULT 'pending',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS accounts (
    account_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    branch_id INTEGER NOT NULL REFERENCES branches(branch_id),
    account_number VARCHAR(40) NOT NULL UNIQUE,
    account_type VARCHAR(40) NOT NULL,
    currency_code CHAR(3) NOT NULL,
    balance NUMERIC(18, 2) NOT NULL DEFAULT 0,
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(account_id),
    counterparty_account_id INTEGER REFERENCES accounts(account_id),
    transaction_type VARCHAR(50) NOT NULL,
    amount NUMERIC(18, 2) NOT NULL,
    amount_usd NUMERIC(18, 2) NOT NULL,
    currency_code CHAR(3) NOT NULL,
    destination_country CHAR(2) REFERENCES countries(country_code),
    description VARCHAR(250),
    reference_number VARCHAR(80) NOT NULL UNIQUE,
    status VARCHAR(30) NOT NULL DEFAULT 'completed',
    is_flagged BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS compliance_rules (
    rule_id INTEGER PRIMARY KEY,
    rule_name VARCHAR(150) NOT NULL,
    rule_type VARCHAR(50) NOT NULL,
    threshold_amount NUMERIC(18, 2),
    max_frequency INTEGER,
    time_window_days INTEGER,
    applies_to VARCHAR(50) NOT NULL DEFAULT 'all',
    severity VARCHAR(30) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id INTEGER PRIMARY KEY,
    transaction_id INTEGER NOT NULL REFERENCES transactions(transaction_id),
    rule_id INTEGER NOT NULL REFERENCES compliance_rules(rule_id),
    assigned_to INTEGER REFERENCES compliance_officers(officer_id),
    severity VARCHAR(30) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'open',
    is_escalated BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS alert_comments (
    comment_id INTEGER PRIMARY KEY,
    alert_id INTEGER NOT NULL REFERENCES alerts(alert_id),
    officer_id INTEGER NOT NULL REFERENCES compliance_officers(officer_id),
    comment TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cases (
    case_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    officer_id INTEGER NOT NULL REFERENCES compliance_officers(officer_id),
    case_type VARCHAR(50) NOT NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'open',
    priority VARCHAR(30) NOT NULL DEFAULT 'medium',
    opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    summary TEXT,
    resolution TEXT
);

CREATE TABLE IF NOT EXISTS case_alerts (
    case_id INTEGER NOT NULL REFERENCES cases(case_id),
    alert_id INTEGER NOT NULL REFERENCES alerts(alert_id),
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    added_by INTEGER REFERENCES compliance_officers(officer_id),
    PRIMARY KEY (case_id, alert_id)
);

CREATE TABLE IF NOT EXISTS risk_scores (
    score_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    score NUMERIC(5, 2) NOT NULL,
    score_level VARCHAR(30) NOT NULL,
    computed_by VARCHAR(50) NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reasoning TEXT
);

CREATE TABLE IF NOT EXISTS regulatory_reports (
    report_id INTEGER PRIMARY KEY,
    case_id INTEGER NOT NULL UNIQUE REFERENCES cases(case_id),
    officer_id INTEGER NOT NULL REFERENCES compliance_officers(officer_id),
    report_type VARCHAR(20) NOT NULL,
    regulator VARCHAR(120) NOT NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'draft',
    submitted_at TIMESTAMPTZ,
    deadline TIMESTAMPTZ,
    reference_number VARCHAR(80),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sanctions_list (
    sanction_id INTEGER PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    entity_type VARCHAR(40) NOT NULL,
    country_code CHAR(2) REFERENCES countries(country_code),
    sanction_type VARCHAR(100) NOT NULL,
    listed_by VARCHAR(120) NOT NULL,
    listed_at DATE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS pep_list (
    pep_id INTEGER PRIMARY KEY,
    full_name VARCHAR(150) NOT NULL,
    position VARCHAR(150) NOT NULL,
    country_code CHAR(2) REFERENCES countries(country_code),
    pep_level VARCHAR(50) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    since_date DATE,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS transaction_patterns (
    pattern_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    avg_transaction NUMERIC(18, 2) NOT NULL,
    max_transaction NUMERIC(18, 2) NOT NULL,
    monthly_volume NUMERIC(18, 2) NOT NULL,
    typical_countries TEXT,
    international_pct NUMERIC(5, 2) NOT NULL DEFAULT 0,
    cash_pct NUMERIC(5, 2) NOT NULL DEFAULT 0,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS monthly_reports (
    report_id INTEGER PRIMARY KEY,
    branch_id INTEGER NOT NULL REFERENCES branches(branch_id),
    report_month DATE NOT NULL,
    total_transactions INTEGER NOT NULL DEFAULT 0,
    total_volume_usd NUMERIC(18, 2) NOT NULL DEFAULT 0,
    total_alerts INTEGER NOT NULL DEFAULT 0,
    total_cases INTEGER NOT NULL DEFAULT 0,
    sars_filed INTEGER NOT NULL DEFAULT 0,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (branch_id, report_month)
);

CREATE TABLE IF NOT EXISTS audit_log (
    log_id INTEGER PRIMARY KEY,
    officer_id INTEGER REFERENCES compliance_officers(officer_id),
    case_id INTEGER REFERENCES cases(case_id),
    alert_id INTEGER REFERENCES alerts(alert_id),
    action VARCHAR(80) NOT NULL,
    entity_type VARCHAR(80) NOT NULL,
    entity_id INTEGER,
    details TEXT,
    ip_address VARCHAR(80),
    action_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transactions_account_created
    ON transactions(account_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_transaction
    ON alerts(transaction_id);
CREATE INDEX IF NOT EXISTS idx_alerts_status
    ON alerts(status);
CREATE INDEX IF NOT EXISTS idx_cases_customer
    ON cases(customer_id);
CREATE INDEX IF NOT EXISTS idx_risk_scores_customer_computed
    ON risk_scores(customer_id, computed_at DESC);
CREATE INDEX IF NOT EXISTS idx_transaction_patterns_customer_computed
    ON transaction_patterns(customer_id, computed_at DESC);
